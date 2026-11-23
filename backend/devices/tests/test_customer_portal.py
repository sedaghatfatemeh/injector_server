from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from devices.models import AuditEntry, Customer, CustomerMembership, Device
from .test_api import device_client, device_pair, staff_user
from .test_customer_membership import portal_user
from .test_staff_auth import sign_in
from .test_staff_users import admin_client

pytestmark = pytest.mark.django_db
ACCOUNTS = "/api/v1/customer-users/"
DEVICES = "/api/v1/customer/devices/"
SUMMARY = "/api/v1/customer/summary/"
PASSWORD = "Correct-Horse-42!"


@pytest.fixture(autouse=True)
def reset_throttle_cache():
    cache.clear()


def test_superadmin_provisions_customer_and_deactivates_existing_session_with_audits():
    client, admin = admin_client()
    org = Customer.objects.create(organization_name="Workshop", contact_name="Owner")
    response = client.post(ACCOUNTS, {"email": " NEW@Example.Test ", "password": PASSWORD, "customer": org.pk}, format="json")
    assert response.status_code == 201
    user = get_user_model().objects.get(pk=response.data["id"])
    assert user.check_password(PASSWORD) and not user.is_staff and not user.is_superuser
    assert response.data["organization"]["id"] == org.pk
    assert user.email == "new@example.test"
    assert not {"password", "username", "groups", "user_permissions"} & set(response.data)
    customer = APIClient()
    assert sign_in(customer, user).status_code == 200
    assert customer.get(SUMMARY).status_code == 200
    assert client.patch(f"{ACCOUNTS}{user.pk}/", {"is_active": False}, format="json").status_code == 200
    assert customer.get(SUMMARY).status_code == 403
    assert client.patch(f"{ACCOUNTS}{user.pk}/", {"is_active": True}, format="json").status_code == 200
    assert sign_in(customer, user).status_code == 200
    entries = AuditEntry.objects.filter(actor=admin, target_id=str(user.pk))
    assert entries.filter(action="customer_user.created").count() == 1
    assert entries.filter(action="customer_user.status_changed").count() == 2
    assert PASSWORD not in str(list(entries.values("details")))
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("kind", ["anonymous", "support", "customer", "device"])
def test_only_superadmin_can_list_provision_or_change_customer_accounts(kind):
    user = portal_user()
    client = APIClient()
    if kind == "device":
        device, token = device_pair()
        client = device_client(token)
    elif kind != "anonymous":
        client.force_login(user if kind == "customer" else staff_user(support=True))
    for method, url, body in [("get", ACCOUNTS, {}), ("post", ACCOUNTS, {"email": "x@example.test", "password": PASSWORD,
                                                                           "customer": user.customer_membership.customer_id}),
                              ("patch", f"{ACCOUNTS}{user.pk}/", {"is_active": False})]:
        response = getattr(client, method)(url, body, format="json")
        assert response.status_code == 403
    user.refresh_from_db()
    assert user.is_active and get_user_model().objects.count() == (2 if kind == "support" else 1)


@pytest.mark.parametrize("field,value", [("is_staff", True), ("is_superuser", True), ("role", "super_admin"),
                                         ("groups", [1]), ("is_active", False)])
def test_customer_provisioning_rejects_privilege_or_status_injection(field, value):
    client, _ = admin_client()
    org = Customer.objects.create(organization_name="Workshop", contact_name="Owner")
    response = client.post(ACCOUNTS, {"email": "new@example.test", "password": PASSWORD, "customer": org.pk,
                                     field: value}, format="json")
    assert response.status_code == 400 and not CustomerMembership.objects.exists()


def test_customer_provisioning_validation_and_atomic_audit_rollback():
    client, _ = admin_client()
    org = Customer.objects.create(organization_name="Workshop", contact_name="Owner")
    data = {"email": "new@example.test", "password": PASSWORD, "customer": org.pk}
    assert client.post(ACCOUNTS, {**data, "password": "12345678"}, format="json").status_code == 400
    org.is_archived = True
    org.save()
    assert client.post(ACCOUNTS, data, format="json").status_code == 400
    org.is_archived = False
    org.save()
    with patch("devices.portal.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            client.post(ACCOUNTS, data, format="json")
    assert not get_user_model().objects.filter(email=data["email"]).exists()
    assert not CustomerMembership.objects.exists()
    assert client.post(ACCOUNTS, data, format="json").status_code == 201
    assert client.post(ACCOUNTS, {**data, "email": data["email"].upper()}, format="json").status_code == 400
    assert client.post("/api/v1/staff-users/", {"email": data["email"], "password": PASSWORD}, format="json").status_code == 400


def test_status_changes_cannot_reassign_customer_or_roles_and_rollback_on_audit_failure():
    client, _ = admin_client()
    user = portal_user()
    url = f"{ACCOUNTS}{user.pk}/"
    for data in [{"customer": user.customer_membership.customer_id}, {"email": "other@example.test"},
                 {"role": "super_admin"}, {"password": PASSWORD}, {"is_staff": True}]:
        assert client.patch(url, data, format="json").status_code == 400
    with patch("devices.portal.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            client.patch(url, {"is_active": False}, format="json")
    user.refresh_from_db()
    assert user.is_active
    assert client.get(f"/admin/auth/user/{user.pk}/change/").status_code == 302


def test_customer_account_writes_require_csrf_and_archived_org_cannot_be_reactivated():
    client, _ = admin_client(csrf=True)
    user = portal_user()
    url = f"{ACCOUNTS}{user.pk}/"
    assert client.patch(url, {"is_active": False}, format="json").status_code == 403
    token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
    assert client.patch(url, {"is_active": False}, format="json", HTTP_X_CSRFTOKEN=token).status_code == 200
    Customer.objects.filter(pk=user.customer_membership.customer_id).update(is_archived=True)
    assert client.patch(url, {"is_active": True}, format="json", HTTP_X_CSRFTOKEN=token).status_code == 400


def portal_client(user=None):
    user = user or portal_user()
    client = APIClient()
    client.force_login(user)
    return client, user


def test_device_scope_safe_fields_foreign_lookup_search_filter_and_summary():
    client, user = portal_client()
    now = timezone.now()
    own = Device.objects.create(customer=user.customer_membership.customer, serial_number="OWN-001", model_name="M1",
                                last_seen_at=now, site_contact_phone="PRIVATE-CONTACT", location="Tehran")
    foreign, _ = device_pair()
    archived = Device.objects.create(customer=own.customer, serial_number="ARCHIVED", model_name="M1", is_archived=True)
    result = client.get(DEVICES)
    assert result.status_code == 200 and result.data["count"] == 1
    assert result.data["results"][0]["id"] == own.pk
    assert set(result.data["results"][0]) == {"id", "serial_number", "model_name", "software_version", "location", "last_seen_at", "is_online"}
    assert "PRIVATE-CONTACT" not in str(result.data) and "no-store" in result["Cache-Control"]
    assert client.get(f"{DEVICES}{own.pk}/").status_code == 200
    absent = client.get(f"{DEVICES}999999/")
    assert client.get(f"{DEVICES}{foreign.pk}/").data == absent.data
    assert client.get(f"{DEVICES}{archived.pk}/").status_code == 404
    assert client.get(DEVICES, {"search": foreign.serial_number}).data["count"] == 0
    assert client.get(DEVICES, {"search": "M1", "online": "true"}).data["count"] == 1
    assert client.get(DEVICES, {"online": "false"}).data["count"] == 0
    summary = client.get(SUMMARY).data
    assert {key: summary[key] for key in ["device_count", "online_count", "offline_count"]} == {
        "device_count": 1, "online_count": 1, "offline_count": 0}
    assert set(summary) == {"device_count", "online_count", "offline_count", "generated_at", "online_window_minutes"}


@pytest.mark.parametrize("params", [{"customer": "1"}, {"customer_id": "1"}, {"ordering": "customer"},
                                   {"is_archived": "true"}, {"online": "invalid"}, {"online": ["true", "false"]}])
def test_customer_api_rejects_unknown_scope_filters_and_duplicate_parameters(params):
    client, _ = portal_client()
    assert client.get(DEVICES, params).status_code == 400
    assert client.get(SUMMARY, {"customer": "1"}).status_code == 400


def test_pagination_counts_and_reassignment_follow_current_ownership():
    client, user = portal_client()
    other = portal_user("second@example.test")
    records = Device.objects.bulk_create([Device(customer=user.customer_membership.customer, model_name="M1",
                                                serial_number=f"OWN-{i:03}") for i in range(51)])
    Device.objects.create(customer=other.customer_membership.customer, model_name="M1", serial_number="FOREIGN")
    assert client.get(DEVICES).data["count"] == 51
    second = client.get(DEVICES, {"page": 2})
    assert len(second.data["results"]) == 1 and second.data["count"] == 51
    moved = records[0]
    Device.objects.filter(pk=moved.pk).update(customer=other.customer_membership.customer)
    assert client.get(f"{DEVICES}{moved.pk}/").status_code == 404
    assert client.get(SUMMARY).data["device_count"] == 50
    other_client, _ = portal_client(other)
    assert other_client.get(f"{DEVICES}{moved.pk}/").status_code == 200


def test_configurable_online_boundary_never_connected_and_empty_organization(settings):
    settings.DEVICE_ONLINE_WINDOW_MINUTES = 7
    client, user = portal_client()
    assert client.get(SUMMARY).data["device_count"] == 0
    now = timezone.now()
    for serial, seen in [("BOUNDARY", now - timedelta(minutes=7)), ("OLD", now - timedelta(minutes=7, microseconds=1)),
                         ("NEVER", None)]:
        Device.objects.create(customer=user.customer_membership.customer, serial_number=serial, model_name="M1", last_seen_at=seen)
    with patch("devices.portal.timezone.now", return_value=now):
        data = client.get(DEVICES).data["results"]
        assert {d["serial_number"]: d["is_online"] for d in data} == {"BOUNDARY": True, "OLD": False, "NEVER": False}
        summary = client.get(SUMMARY).data
        assert summary["online_count"] == 1 and summary["offline_count"] == 2 and summary["online_window_minutes"] == 7


def test_customer_endpoints_reject_writes_staff_and_revoked_membership():
    client, user = portal_client()
    for method in ["post", "put", "patch", "delete"]:
        assert getattr(client, method)(DEVICES, {}, format="json").status_code == 405
    CustomerMembership.objects.filter(user=user).delete()
    assert client.get(DEVICES).status_code == 403 and client.get(SUMMARY).status_code == 403
    client.force_login(staff_user(superuser=True))
    assert client.get(DEVICES).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_concurrent_staff_and_customer_api_creation_share_email_uniqueness():
    client, admin = admin_client()
    org = Customer.objects.create(organization_name="Workshop", contact_name="Owner")
    barrier = Barrier(2)

    def create(kind):
        try:
            local = APIClient()
            local.force_login(get_user_model().objects.get(pk=admin.pk))
            barrier.wait(timeout=15)
            data = {"email": "race@example.test", "password": PASSWORD}
            if kind == "customer":
                data["customer"] = org.pk
            return local.post(ACCOUNTS if kind == "customer" else "/api/v1/staff-users/", data, format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(create, ["customer", "staff"]))
    assert sorted(outcomes) == [201, 400]
    assert get_user_model().objects.filter(email="race@example.test").count() == 1
