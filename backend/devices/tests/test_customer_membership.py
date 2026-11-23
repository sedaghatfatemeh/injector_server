import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework.test import APIClient

from devices.access import customer_membership, staff_role
from devices.models import Customer, CustomerMembership, Device

pytestmark = pytest.mark.django_db


def portal_user(email="customer@example.test", customer=None):
    customer = customer or Customer.objects.create(organization_name="Workshop", contact_name="Owner")
    user = get_user_model().objects.create_user(username=email, email=email, password="Correct-Horse-42!")
    CustomerMembership.objects.create(user=user, customer=customer)
    return user


def test_one_organization_per_user_many_accounts_per_organization_and_protected_ownership():
    user = portal_user()
    membership = customer_membership(user)
    other = portal_user("other@example.test", membership.customer)
    assert customer_membership(other).customer_id == membership.customer_id
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomerMembership.objects.create(user=user, customer=membership.customer)
    with pytest.raises(ProtectedError):
        membership.customer.delete()
    user.delete()
    assert not CustomerMembership.objects.filter(pk=membership.pk).exists()
    assert Customer.objects.filter(pk=membership.customer_id).exists()


@pytest.mark.parametrize("kind", ["missing", "inactive", "archived", "staff", "superuser", "support"])
def test_customer_eligibility_fails_closed_and_does_not_trust_cached_membership(kind):
    user = portal_user()
    membership = user.customer_membership  # Deliberately populate Django's relation cache.
    if kind == "missing":
        membership.delete()
    elif kind == "archived":
        Customer.objects.filter(pk=membership.customer_id).update(is_archived=True)
    elif kind == "support":
        user.groups.add(Group.objects.get_or_create(name="support")[0])
    else:
        setattr(user, {"inactive": "is_active", "staff": "is_staff", "superuser": "is_superuser"}[kind], kind != "inactive")
        user.save()
    assert customer_membership(user) is None
    assert staff_role(user) is None


@pytest.mark.parametrize("identity", [AnonymousUser(), Device(serial_number="NOT-A-USER")])
def test_nonbrowser_identities_have_no_customer_or_staff_role(identity):
    assert customer_membership(identity) is None and staff_role(identity) is None


@pytest.mark.parametrize("kind", ["is_staff", "is_superuser", "support"])
def test_membership_validation_rejects_mixed_staff_identity(kind):
    user = portal_user()
    if kind == "support":
        user.groups.add(Group.objects.get_or_create(name="support")[0])
    else:
        setattr(user, kind, True)
        user.save()
    with pytest.raises(ValidationError):
        user.customer_membership.full_clean()


def test_mixed_identity_cannot_bypass_staff_api_or_native_admin():
    user = portal_user()
    user.is_staff = user.is_superuser = True
    user.save()
    client = APIClient()
    client.force_login(user)
    for url in ["/api/v1/devices/", "/api/v1/staff-users/", "/api/v1/dashboard/summary/"]:
        assert client.get(url).status_code == 403
    assert client.get("/admin/").status_code == 302
