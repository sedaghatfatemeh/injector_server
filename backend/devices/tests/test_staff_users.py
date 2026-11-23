from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from rest_framework.test import APIClient

from devices.models import AuditEntry
from .test_api import device_client, device_pair, staff_user


pytestmark = pytest.mark.django_db
URL = "/api/v1/staff-users/"
PASSWORD = "Device-Support-74!"


@pytest.fixture(autouse=True)
def reset_throttles():
    cache.clear()


def payload(**overrides):
    return {"email": "employee@example.test", "first_name": "Nadia", "last_name": "Shargh", "password": PASSWORD, **overrides}


def admin_client(admin=None, *, csrf=False):
    admin = admin or staff_user(superuser=True)
    client = APIClient(enforce_csrf_checks=csrf)
    client.force_login(admin)
    return client, admin


@pytest.mark.parametrize("role", ["support", "super_admin"])
def test_admin_can_provision_staff_who_can_sign_in(role):
    client, admin = admin_client()
    response = client.post(URL, payload(email=" Employee@Example.Test ", role=role), format="json")
    assert response.status_code == 201
    assert response.data["email"] == "employee@example.test"
    assert response.data["role"] == role
    assert "password" not in response.data and "username" not in response.data
    user = get_user_model().objects.get(pk=response.data["id"])
    assert user.is_staff and user.is_active
    assert user.is_superuser is (role == "super_admin")
    assert user.groups.filter(name="support").exists() is (role == "support")
    assert user.password != PASSWORD and user.check_password(PASSWORD)
    audit = AuditEntry.objects.get(action="staff.created", target_id=str(user.pk))
    assert audit.actor == admin and audit.details == {"role": role}
    assert PASSWORD not in str(audit.details) and user.password not in str(audit.details)

    login_client = APIClient(enforce_csrf_checks=True)
    csrf = login_client.get("/api/v1/auth/csrf/").data["csrfToken"]
    login = login_client.post("/api/v1/auth/login/", {
        "email": "EMPLOYEE@example.test", "password": PASSWORD,
    }, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert login.status_code == 200 and login.data["role"] == role
    assert login_client.get("/api/v1/customers/").status_code == 200
    assert login_client.get(URL).status_code == (200 if role == "super_admin" else 403)


def test_support_cannot_view_or_provision_users_and_denial_is_audited():
    support = staff_user(support=True)
    client = APIClient()
    client.force_login(support)
    assert client.get(URL).status_code == 403
    assert client.post(URL, payload(role="super_admin"), format="json").status_code == 403
    assert not get_user_model().objects.filter(email="employee@example.test").exists()
    assert AuditEntry.objects.filter(actor=support, action="staff.provision_denied", outcome="denied").exists()
    assert PASSWORD not in str(list(AuditEntry.objects.values("details")))


def test_anonymous_and_device_credentials_cannot_view_or_provision_staff():
    _, token = device_pair()
    for client in (APIClient(), device_client(token)):
        assert client.get(URL).status_code == 403
        assert client.post(URL, payload(), format="json").status_code == 403
    assert not get_user_model().objects.filter(email="employee@example.test").exists()


@pytest.mark.parametrize("password", ["123", "password", "Nadia"])
def test_staff_creation_rejects_weak_passwords(password):
    client, _ = admin_client()
    response = client.post(URL, payload(password=password), format="json")
    assert response.status_code == 400 and "password" in response.data
    assert not get_user_model().objects.filter(email="employee@example.test").exists()
    assert not AuditEntry.objects.filter(action="staff.created").exists()


def test_staff_creation_requires_valid_email_and_role():
    client, _ = admin_client()
    assert client.post(URL, payload(email="invalid"), format="json").status_code == 400
    assert client.post(URL, payload(role="customer"), format="json").status_code == 400


def test_staff_creation_rejects_existing_email_including_inactive_accounts():
    client, _ = admin_client()
    existing = get_user_model().objects.create_user(username="old-account", email="Employee@Example.Test", is_active=False)
    response = client.post(URL, payload(), format="json")
    assert response.status_code == 400 and "email" in response.data
    assert get_user_model().objects.filter(email__iexact=existing.email).count() == 1


def test_long_email_is_supported_without_exposing_internal_username():
    client, _ = admin_client()
    email = "a" * 60 + "@" + "b" * 60 + "." + "c" * 60 + ".test"
    response = client.post(URL, payload(email=email), format="json")
    assert response.status_code == 201 and response.data["email"] == email


def test_untrusted_privilege_fields_cannot_override_support_role():
    client, _ = admin_client()
    response = client.post(URL, payload(is_superuser=True, is_staff=False, is_active=False, groups=[1]), format="json")
    assert response.status_code == 201
    user = get_user_model().objects.get(pk=response.data["id"])
    assert user.is_staff and user.is_active and not user.is_superuser
    assert user.groups.filter(name="support").exists()


def test_user_list_is_paginated_searchable_and_hides_nonstaff_accounts():
    client, _ = admin_client()
    user = staff_user(support=True)
    get_user_model().objects.create_user(username="customer", email="customer@example.test")
    response = client.get(URL, {"search": user.email})
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == user.pk
    assert "password" not in response.data["results"][0]
    assert client.get(URL, {"search": "customer@example.test"}).data["count"] == 0
    # No edit/delete endpoint is exposed by this provisioning slice.
    assert client.delete(f"{URL}{user.pk}/").status_code == 404


def test_staff_creation_requires_csrf_and_session_expiry_removes_access():
    client, _ = admin_client(csrf=True)
    csrf = client.get("/api/v1/auth/csrf/").data["csrfToken"]
    assert client.post(URL, payload(), format="json").status_code == 403
    assert client.post(URL, payload(), format="json", HTTP_X_CSRFTOKEN=csrf).status_code == 201
    session = client.session
    session.set_expiry(-1)
    session.save()
    assert client.get(URL).status_code == 403


def test_audit_failure_does_not_leave_an_unaudited_staff_account():
    client, _ = admin_client()
    with patch("devices.views.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post(URL, payload(), format="json")
    assert not get_user_model().objects.filter(email="employee@example.test").exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_provisioning_cannot_duplicate_login_email():
    admin = staff_user(superuser=True)
    barrier = Barrier(2)

    def provision(_):
        try:
            client = APIClient()
            client.force_authenticate(admin)
            barrier.wait(timeout=10)
            return client.post(URL, payload(), format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(provision, range(2)))
    assert sorted(responses) == [201, 400]
    assert get_user_model().objects.filter(email__iexact="employee@example.test").count() == 1
    assert AuditEntry.objects.filter(action="staff.created").count() == 1
