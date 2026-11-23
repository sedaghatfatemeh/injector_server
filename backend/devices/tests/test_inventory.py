from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import uuid

import pytest
from django.db import IntegrityError, connections
from django.utils import timezone
from rest_framework.test import APIClient

from devices.authentication import issue_device_token
from devices.models import AuditEntry, Customer, Device, SoftwareRelease, UpdateAssignment
from devices.serializers import DeviceSerializer, CustomerSerializer
from .test_api import device_pair, device_client, event_payload, staff_user


pytestmark = pytest.mark.django_db


def admin_client():
    client = APIClient()
    client.force_authenticate(staff_user(superuser=True))
    return client


def customer(**values):
    return Customer.objects.create(organization_name="Workshop", contact_name="Nadia", contact_phone="123", **values)


def test_customer_normalization_and_phone_search_include_legacy_formats():
    client = admin_client()
    response = client.post("/api/v1/customers/", {"organization_name": "  Fleet Workshop  ", "contact_name": "  Nadia  ",
                           "contact_email": " SERVICE@EXAMPLE.TEST ", "contact_phone": "+۹۸ (۲۱) ۱۲۳۴-۵۶۷۸"}, format="json")
    assert response.status_code == 201 and response.data["device_count"] == 0
    saved = Customer.objects.get(pk=response.data["id"])
    assert saved.organization_name == "Fleet Workshop" and saved.contact_name == "Nadia"
    assert saved.contact_email == "service@example.test" and saved.contact_phone == "+982112345678"
    for search in ("Fleet Nadia", "+۹۸ (۲۱) ۱۲۳۴-۵۶۷۸", "+982112345678", "SERVICE@EXAMPLE.TEST"):
        assert client.get("/api/v1/customers/", {"search": search}).data["count"] == 1
    legacy = Customer.objects.create(organization_name="Legacy", contact_name="Ali", contact_phone="۰۹۱۲ (۱۲۳)-۴۵۶۷")
    result = client.get("/api/v1/customers/", {"search": "09121234567"})
    assert result.status_code == 200 and result.data["results"][0]["id"] == legacy.pk
    legacy.refresh_from_db()
    assert legacy.contact_phone == "۰۹۱۲ (۱۲۳)-۴۵۶۷"


@pytest.mark.parametrize("values", [
    {"organization_name": " "}, {"contact_name": " "}, {"contact_email": "", "contact_phone": ""},
    {"contact_email": "not-an-email", "contact_phone": ""},
])
def test_customer_minimum_fields_are_validated(values):
    response = admin_client().post("/api/v1/customers/", {"organization_name": "Workshop", "contact_name": "Ali",
                                    "contact_email": "service@example.test", "contact_phone": "123", **values}, format="json")
    assert response.status_code == 400 and not Customer.objects.exists()


def test_archived_customer_cannot_receive_new_assignments_and_reassignment_is_audited():
    client = admin_client()
    device, _ = device_pair()
    original_customer_id = device.customer_id
    archived = customer(is_archived=True)
    target = customer()
    creation = client.post("/api/v1/devices/", {"serial_number": "ARCHIVED-TARGET", "model_name": "M1", "customer": archived.pk}, format="json")
    assert creation.status_code == 400 and "customer" in creation.data
    url = f"/api/v1/devices/{device.pk}/"
    assert client.patch(url, {"customer": archived.pk}, format="json").status_code == 400
    moved = client.patch(url, {"customer": target.pk, "site_contact_phone": "+۹۸ (۲۱) ۱۲۳۴-۵۶۷۸"}, format="json")
    assert moved.status_code == 200 and moved.data["site_contact_phone"] == "+982112345678"
    audit = AuditEntry.objects.get(action="device.updated", target_id=str(device.pk))
    assert audit.details["customer_changed"]
    assert audit.details["before"]["customer_id"] == original_customer_id
    assert audit.details["after"]["customer_id"] == target.pk


def test_device_registration_and_readonly_operational_facts_have_consistent_responses():
    client = admin_client()
    owner = customer()
    response = client.post("/api/v1/devices/", {"serial_number": "  REGISTER-001  ", "model_name": "M1", "customer": owner.pk,
                           "software_version": "1.0.0", "install_state": "idle", "is_online": True}, format="json")
    assert response.status_code == 201
    assert response.data["serial_number"] == "REGISTER-001"
    assert response.data["is_online"] is False and response.data["active_fault_count"] == 0
    assert response.data["install_state"] == "unknown" and response.data["customer_is_archived"] is False
    device = Device.objects.get(pk=response.data["id"])
    url = f"/api/v1/devices/{device.pk}/"
    assert client.patch(url, {"software_version": "1.1.0"}, format="json").data["software_version"] == "1.1.0"
    token = issue_device_token(device)
    assert device_client(token).post("/api/v1/device/check-in/", {"software_version": "2.0.0", "install_state": "testing"}, format="json").status_code == 200
    device.refresh_from_db()
    seen = device.last_seen_at
    edited = client.patch(url, {"software_version": "fake-version", "install_state": "idle", "last_seen_at": "2099-01-01T00:00:00Z",
                           "active_fault_count": 999, "location": "Depot"}, format="json")
    assert edited.status_code == 200 and edited.data["software_version"] == "2.0.0"
    assert edited.data["install_state"] == "testing" and edited.data["active_fault_count"] == 0
    device.refresh_from_db()
    assert device.last_seen_at == seen and device.location == "Depot"


def test_inventory_edit_keeps_a_check_in_that_arrived_after_validation():
    device, _ = device_pair(version="1.0.0")
    received_at = timezone.now()
    original = DeviceSerializer.is_valid

    def validate_then_check_in(serializer, *args, **kwargs):
        result = original(serializer, *args, **kwargs)
        Device.objects.filter(pk=device.pk).update(last_seen_at=received_at, software_version="3.0.0", install_state="testing")
        return result

    with patch.object(DeviceSerializer, "is_valid", validate_then_check_in):
        response = admin_client().patch(f"/api/v1/devices/{device.pk}/", {"location": "New depot", "software_version": "1.0.0"}, format="json")
    assert response.status_code == 200 and response.data["is_online"] is True
    device.refresh_from_db()
    assert device.last_seen_at == received_at and device.software_version == "3.0.0"
    assert device.install_state == "testing" and device.location == "New depot"


@pytest.mark.parametrize("operation", ["customer_create", "customer_update", "customer_archive", "device_create", "device_update", "device_archive"])
def test_inventory_and_audit_writes_are_atomic_and_storage_failures_are_not_serial_conflicts(operation):
    device, _ = device_pair()
    owner = device.customer
    client = admin_client()
    counts = (Customer.objects.count(), Device.objects.count())
    operations = {
        "customer_create": ("post", "/api/v1/customers/", {"organization_name": "New", "contact_name": "Ali", "contact_phone": "123"}),
        "customer_update": ("patch", f"/api/v1/customers/{owner.pk}/", {"contact_name": "Changed"}),
        "customer_archive": ("delete", f"/api/v1/customers/{owner.pk}/", {}),
        "device_create": ("post", "/api/v1/devices/", {"serial_number": "NEW-SERIAL", "model_name": "M1", "customer": owner.pk}),
        "device_update": ("patch", f"/api/v1/devices/{device.pk}/", {"location": "Changed"}),
        "device_archive": ("delete", f"/api/v1/devices/{device.pk}/", {}),
    }
    method, path, payload = operations[operation]
    with patch("devices.views.AuditEntry.objects.create", side_effect=IntegrityError("audit storage unavailable")):
        with pytest.raises(IntegrityError, match="audit storage unavailable"):
            getattr(client, method)(path, payload, format="json")
    assert (Customer.objects.count(), Device.objects.count()) == counts
    device.refresh_from_db()
    owner.refresh_from_db()
    assert not device.is_archived and not owner.is_archived and device.location == "" and owner.contact_name == "Nadia"


def test_archived_device_history_and_customer_devices_are_explicitly_retrievable():
    device, token = device_pair()
    client = admin_client()
    payload = event_payload()
    assert device_client(token).post("/api/v1/device/events/", {"events": [payload]}, format="json").status_code == 200
    publisher = staff_user(superuser=True)
    release = SoftwareRelease.objects.create(version="2.0.0", created_by=publisher, package_url="https://packages.example.test/app.whl", sha256="a" * 64)
    assignment = UpdateAssignment.objects.create(device=device, release=release)
    url = f"/api/v1/devices/{device.pk}/"
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get("/api/v1/devices/").data["count"] == 0
    assert client.get(url + "events/", {"is_archived": "true"}).data["results"][0]["event_id"] == payload["event_id"]
    assert client.get(url + "updates/", {"is_archived": "true"}).data["results"][0]["id"] == assignment.pk
    children = f"/api/v1/customers/{device.customer_id}/devices/"
    assert client.get(children).data["count"] == 0
    assert client.get(children, {"include_archived_devices": "true"}).data["count"] == 1
    assert device_client(token).post("/api/v1/device/check-in/", {}, format="json").status_code == 401
    assert client.patch(url + "?is_archived=true", {"is_archived": False}, format="json").status_code == 200
    assert Device.objects.get(pk=device.pk).serial_number == device.serial_number
    assert device.events.count() == 1


def test_customer_archive_is_independent_and_history_requires_explicit_parent_opt_in():
    device, token = device_pair()
    client = admin_client()
    device_client(token).post("/api/v1/device/events/", {"events": [event_payload()]}, format="json")
    owner_url = f"/api/v1/customers/{device.customer_id}/"
    assert client.delete(owner_url).status_code == 204
    device.refresh_from_db()
    assert not device.is_archived
    assert client.get("/api/v1/customers/").data["count"] == 0
    inventory = client.get("/api/v1/devices/")
    assert inventory.data["count"] == 1 and inventory.data["results"][0]["customer_is_archived"] is True
    assert client.get(owner_url + "devices/", {"is_archived": "true"}).data["count"] == 1
    assert client.get(f"/api/v1/devices/{device.pk}/events/").data["count"] == 0
    assert client.get(f"/api/v1/devices/{device.pk}/events/", {"device__customer__is_archived": "true"}).data["count"] == 1
    assert client.patch(f"/api/v1/devices/{device.pk}/", {"customer": device.customer_id, "location": "Preserved owner"}, format="json").status_code == 200
    assert device_client(token).post("/api/v1/device/check-in/", {}, format="json").status_code == 200


def test_restoring_a_device_requires_an_active_customer():
    device, _ = device_pair()
    device.is_archived = True
    device.save(update_fields=["is_archived"])
    Customer.objects.filter(pk=device.customer_id).update(is_archived=True)
    client = admin_client()
    url = f"/api/v1/devices/{device.pk}/?is_archived=true"
    response = client.patch(url, {"is_archived": False}, format="json")
    assert response.status_code == 400 and "customer" in response.data
    active = customer()
    assert client.patch(url, {"is_archived": False, "customer": active.pk}, format="json").status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/customers/?is_archived=", "/api/v1/devices/?is_archived=maybe"])
def test_archive_filters_require_explicit_booleans(path):
    assert admin_client().get(path).status_code == 400


def test_support_search_filters_and_customer_scoped_pagination_are_stable():
    owner = customer()
    other, _ = device_pair()
    devices = Device.objects.bulk_create([Device(serial_number=f"C-{i:04d}", model_name="M1", customer=owner) for i in range(52)])
    clients = APIClient()
    clients.force_authenticate(staff_user(support=True))
    path = f"/api/v1/customers/{owner.pk}/devices/"
    first = clients.get(path)
    second = clients.get(path, {"page": 2})
    assert first.data["count"] == 52 and len(first.data["results"]) == 50
    ids = [row["id"] for row in first.data["results"] + second.data["results"]]
    assert ids == [device.pk for device in devices] and other.pk not in ids
    assert clients.get("/api/v1/devices/", {"customer": owner.pk, "model_name": "M1", "online": "false", "has_active_faults": "false"}).data["count"] == 52
    assert clients.get("/api/v1/devices/", {"customer": owner.pk, "online": "true"}).data["count"] == 0
    same_names = Customer.objects.bulk_create([Customer(organization_name="Same organization", contact_name="Ali", contact_phone="123") for _ in range(52)])
    params = {"search": "Same organization", "ordering": "organization_name"}
    page1, page2 = clients.get("/api/v1/customers/", params), clients.get("/api/v1/customers/", {**params, "page": 2})
    assert [row["id"] for row in page1.data["results"] + page2.data["results"]] == sorted(row.pk for row in same_names)


@pytest.mark.django_db(transaction=True)
def test_concurrent_contact_edits_cannot_remove_both_contact_methods():
    owner = Customer.objects.create(organization_name="Concurrent", contact_name="Ali", contact_phone="123", contact_email="a@example.test")
    admin = staff_user(superuser=True)
    barrier = Barrier(2)
    original = CustomerSerializer.is_valid

    def validated(serializer, *args, **kwargs):
        result = original(serializer, *args, **kwargs)
        barrier.wait(timeout=10)
        return result

    def edit(payload):
        try:
            client = APIClient()
            client.force_authenticate(admin)
            return client.patch(f"/api/v1/customers/{owner.pk}/", payload, format="json").status_code
        finally:
            connections.close_all()

    with patch.object(CustomerSerializer, "is_valid", validated), ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, [{"contact_phone": ""}, {"contact_email": ""}]))
    assert sorted(results) == [200, 400]
    owner.refresh_from_db()
    assert owner.contact_phone or owner.contact_email


@pytest.mark.django_db(transaction=True)
def test_concurrent_serial_edits_return_a_field_conflict_instead_of_server_error():
    first, _ = device_pair()
    second, _ = device_pair()
    admin = staff_user(superuser=True)
    serial = "SHARED-" + uuid.uuid4().hex
    barrier = Barrier(2)
    original = DeviceSerializer.is_valid

    def validated(serializer, *args, **kwargs):
        result = original(serializer, *args, **kwargs)
        barrier.wait(timeout=10)
        return result

    def edit(device):
        try:
            client = APIClient()
            client.force_authenticate(admin)
            response = client.patch(f"/api/v1/devices/{device.pk}/", {"serial_number": serial}, format="json")
            return response.status_code, "serial_number" in response.data
        finally:
            connections.close_all()

    with patch.object(DeviceSerializer, "is_valid", validated), ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, [first, second]))
    assert sorted(status for status, _ in results) == [200, 400]
    assert all(has_field for _, has_field in results)
    assert Device.objects.filter(serial_number=serial).count() == 1
