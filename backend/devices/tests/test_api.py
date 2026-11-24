from datetime import timedelta
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.db import IntegrityError, close_old_connections, connections
from django.utils import timezone
from rest_framework.test import APIClient

from devices.authentication import digest_device_token, issue_device_token
from devices.models import AuditEntry, Customer, Device, DeviceCredential, DeviceEvent, DeviceFault, SoftwareRelease, UpdateAssignment
from devices.views import available_release_for


pytestmark = pytest.mark.django_db


def test_event_history_filters_and_pagination_preserve_tied_events():
    device, _ = device_pair()
    other, _ = device_pair()
    now = timezone.now()
    expected = DeviceEvent.objects.bulk_create([
        DeviceEvent(device=device, event_id=uuid.uuid4(), occurred_at=now,
                    code="ENGINE_WARN", state="active", summary="Pressure warning")
        for _ in range(51)
    ])
    DeviceEvent.objects.create(device=other, event_id=uuid.uuid4(), occurred_at=now,
                               code="ENGINE_WARN", state="active", summary="Pressure warning")
    DeviceEvent.objects.create(device=device, event_id=uuid.uuid4(), occurred_at=now - timedelta(days=2),
                               code="ENGINE_WARN", state="active", summary="Pressure warning")
    DeviceEvent.objects.create(device=device, event_id=uuid.uuid4(), occurred_at=now,
                               code="ENGINE_WARN", state="resolved", summary="Pressure warning")
    client = APIClient()
    client.force_authenticate(staff_user(support=True))
    params = {
        "device__serial_number__icontains": device.serial_number.lower(),
        "device__customer__organization_name__icontains": "gar",
        "state": "active", "search": "Pressure",
        "occurred_after": (now - timedelta(hours=1)).isoformat(),
        "occurred_before": now.isoformat(),
    }
    first = client.get("/api/v1/events/", params)
    assert first.status_code == 200
    assert first.data["count"] == 51
    assert len(first.data["results"]) == 50
    assert first.data["next"] is not None
    second = client.get("/api/v1/events/", {**params, "page": 2})
    assert second.status_code == 200
    assert second.data["next"] is None
    assert second.data["previous"] is not None
    actual = [item["id"] for item in first.data["results"] + second.data["results"]]
    assert actual == sorted([item.pk for item in expected], reverse=True)
    excluded = client.get("/api/v1/events/", {**params, "device__customer__organization_name__icontains": "missing"})
    assert excluded.data["count"] == 0


@pytest.mark.parametrize("params", [
    {"occurred_after": "2026-02-30T12:00:00Z"},
    {"occurred_before": "2026-13-01T12:00:00Z"},
    {"occurred_after": "2026-01-01T12:00:00"},
    {"occurred_before": "invalid"},
    {"occurred_after": "2026-01-02T12:00:00Z", "occurred_before": "2026-01-01T12:00:00Z"},
])
def test_event_history_rejects_invalid_date_ranges(params):
    client = APIClient()
    client.force_authenticate(staff_user(support=True))
    assert client.get("/api/v1/events/", params).status_code == 400


@pytest.mark.django_db(transaction=True)
def test_concurrent_fault_reports_keep_latest_occurrence():
    device, token = device_pair()
    fault_id = uuid.uuid4()
    now = timezone.now()
    older = event_payload(fault_id=fault_id, state="active", occurred_at=now - timedelta(hours=1))
    newer = event_payload(fault_id=fault_id, state="resolved", occurred_at=now)
    barrier = Barrier(2)

    def deliver(payload):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            response = device_client(token).post("/api/v1/device/events/", {"events": [payload]}, format="json")
            return response.status_code, response.data["results"][0]["status"]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(deliver, [newer, older]))
    assert results == [(200, "accepted"), (200, "accepted")]
    fault = DeviceFault.objects.get(device=device, fault_id=fault_id)
    assert fault.state == "resolved"
    assert fault.latest_event.event_id == uuid.UUID(newer["event_id"])
    assert device.events.count() == 2


def test_projection_failure_rolls_back_event_and_allows_retry():
    device, token = device_pair()
    payload = event_payload(fault_id=uuid.uuid4(), state="active")
    client = device_client(token)
    with patch.object(DeviceFault.objects, "get_or_create", side_effect=IntegrityError("storage failure")):
        with pytest.raises(IntegrityError):
            client.post("/api/v1/device/events/", {"events": [payload]}, format="json")
    assert not device.events.exists()
    device.refresh_from_db()
    assert device.last_seen_at is None
    response = client.post("/api/v1/device/events/", {"events": [payload]}, format="json")
    assert response.data["results"][0]["status"] == "accepted"
    assert DeviceFault.objects.filter(device=device, latest_event__event_id=payload["event_id"]).exists()


def staff_user(*, superuser=False, support=False):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=f"user-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.test", password="Correct-Horse-42!",
        is_staff=True, is_superuser=superuser,
    )
    if support:
        user.groups.add(Group.objects.get_or_create(name="support")[0])
    return user


def device_pair(*, version="1.0.0", last_seen_at=None, model="M1"):
    customer = Customer.objects.create(organization_name="Garage", contact_name="Nadia", contact_phone="123")
    device = Device.objects.create(serial_number=f"PS-{uuid.uuid4()}", model_name=model, customer=customer, software_version=version, last_seen_at=last_seen_at)
    token = issue_device_token(device)
    return device, token


def event_payload(*, event_id=None, fault_id=None, state="info", occurred_at=None, code="ENGINE_WARN"):
    return {
        "event_id": str(event_id or uuid.uuid4()), "fault_id": str(fault_id) if fault_id else None,
        "code": code, "summary": "Reported by device", "occurred_at": (occurred_at or timezone.now()).isoformat(),
        "state": state, "metadata": {"source": "device"},
    }


def device_client(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Device {token}")
    return client


def test_credential_is_only_stored_as_digest_and_revoked_tokens_fail():
    device, token = device_pair()
    credential = DeviceCredential.objects.get(device=device)
    assert credential.token_digest == digest_device_token(token)
    assert token not in credential.token_digest
    response = device_client(token).post("/api/v1/device/check-in/", {"software_version": "1.1.0", "install_state": "idle"}, format="json")
    assert response.status_code == 200
    credential.revoked_at = timezone.now()
    credential.save(update_fields=["revoked_at"])
    assert device_client(token).post("/api/v1/device/check-in/", {}, format="json").status_code == 401


def test_serial_uniqueness_includes_archived_devices_and_other_customers():
    device, _ = device_pair()
    device.is_archived = True
    device.save(update_fields=["is_archived"])
    customer = Customer.objects.create(organization_name="Other workshop", contact_name="Ali", contact_phone="456")
    client = APIClient()
    client.force_authenticate(staff_user(superuser=True))
    payload = {"serial_number": device.serial_number, "customer": customer.pk, "device_model": registration_model()}
    response = client.post("/api/v1/devices/", payload, format="json")
    assert response.status_code == 400 and "serial_number" in response.data
    assert Device.objects.filter(serial_number=device.serial_number).count() == 1
    device.refresh_from_db()
    assert device.customer_id != customer.pk
    assert client.post("/api/v1/devices/", {**payload, "serial_number": "NEW-UNIQUE-001"}, format="json").status_code == 201


def test_event_identity_is_scoped_to_authenticated_device():
    first, first_token = device_pair()
    second, second_token = device_pair()
    event = event_payload()
    for device, token in ((first, first_token), (second, second_token)):
        client = device_client(token)
        first_delivery = client.post("/api/v1/device/events/", {"events": [event]}, format="json")
        retry = client.post("/api/v1/device/events/", {"events": [event]}, format="json")
        assert first_delivery.status_code == retry.status_code == 200
        assert first_delivery.data["results"][0]["status"] == "accepted"
        assert retry.data["results"][0]["status"] == "duplicate"
        assert device.events.filter(event_id=event["event_id"]).count() == 1
    assert DeviceEvent.objects.filter(event_id=event["event_id"]).count() == 2


def test_unauthenticated_staff_api_rejected_support_reads_and_cannot_write():
    customer = Customer.objects.create(organization_name="Garage", contact_name="Nadia", contact_phone="123")
    assert APIClient().get("/api/v1/customers/").status_code == 403
    client = APIClient()
    client.force_authenticate(user=staff_user(support=True))
    assert client.get("/api/v1/customers/").status_code == 200
    assert client.post("/api/v1/customers/", {"organization_name": "New", "contact_name": "Ali", "contact_phone": "555"}, format="json").status_code == 403
    assert customer.pk is not None


def test_staff_login_uses_session_cookie_without_returning_bearer_token():
    user = staff_user(superuser=True)
    client = APIClient(enforce_csrf_checks=True)
    csrf_response = client.get("/api/v1/auth/csrf/")
    csrf = csrf_response.data["csrfToken"]
    response = client.post("/api/v1/auth/login/", {"email": user.email, "password": "Correct-Horse-42!"}, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 200
    assert "token" not in response.data
    assert "sessionid" in client.cookies
    assert AuditEntry.objects.filter(actor=user, action="staff.signed_in").exists()
    assert client.post("/api/v1/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code == 204
    assert client.get("/api/v1/customers/").status_code == 403


def test_duplicate_conflicting_and_immutable_events():
    device, token = device_pair()
    client = device_client(token)
    payload = event_payload()
    first = client.post("/api/v1/device/events/", {"events": [payload]}, format="json")
    duplicate = client.post("/api/v1/device/events/", {"events": [payload]}, format="json")
    conflict = dict(payload, code="DIFFERENT")
    rejected = client.post("/api/v1/device/events/", {"events": [conflict]}, format="json")
    assert [first.data["results"][0]["status"], duplicate.data["results"][0]["status"], rejected.data["results"][0]["status"]] == ["accepted", "duplicate", "rejected"]
    assert device.events.count() == 1
    with pytest.raises(ValueError, match="immutable"):
        event = device.events.get()
        event.summary = "changed"
        event.save()
    assert AuditEntry.objects.filter(action="device.event_id_conflict", outcome="rejected").exists()


def test_rotation_invalidates_old_token_and_device_cannot_access_staff_api():
    device, old_token = device_pair()
    new_token = issue_device_token(device)
    assert DeviceCredential.objects.filter(device=device).count() == 1
    assert device_client(old_token).post("/api/v1/device/check-in/", {}, format="json").status_code == 401
    assert device_client(new_token).post("/api/v1/device/check-in/", {}, format="json").status_code == 200
    assert device_client(new_token).get("/api/v1/customers/").status_code == 403


def test_support_cannot_assign_rollbacks():
    admin = staff_user(superuser=True)
    release = SoftwareRelease.objects.create(version="1.0.0", package_url="https://packages.example/1", sha256="a" * 64, status="published", created_by=admin)
    client = APIClient()
    client.force_authenticate(user=staff_user(support=True))
    assert client.post(f"/api/v1/releases/{release.pk}/rollback/", {}, format="json").status_code == 403


def test_delayed_fault_event_does_not_replace_latest_state_and_rejected_batch_does_not_check_in():
    device, token = device_pair(last_seen_at=timezone.now() - timedelta(hours=1))
    client = device_client(token)
    fault_id = uuid.uuid4()
    now = timezone.now()
    newer = event_payload(fault_id=fault_id, state="resolved", occurred_at=now, code="FUEL_PRESSURE")
    older = event_payload(fault_id=fault_id, state="active", occurred_at=now - timedelta(days=2))
    response = client.post("/api/v1/device/events/", {"events": [newer, older]}, format="json")
    device.refresh_from_db()
    fault = DeviceFault.objects.get(device=device, fault_id=fault_id)
    assert response.status_code == 200
    assert fault.state == "resolved"
    assert fault.latest_event.event_id == uuid.UUID(newer["event_id"])
    assert fault.started_at < fault.latest_event.occurred_at
    assert device.last_seen_at > now - timedelta(minutes=1)
    previous_seen = device.last_seen_at
    bad = event_payload()
    bad["occurred_at"] = "not-a-time"
    client.post("/api/v1/device/events/", {"events": [bad]}, format="json")
    device.refresh_from_db()
    assert device.last_seen_at == previous_seen


def test_check_in_does_not_regress_to_older_server_time():
    device, token = device_pair(last_seen_at=timezone.now() + timedelta(minutes=5), version="2.0.0")
    response = device_client(token).post("/api/v1/device/check-in/", {"software_version": "1.0.0", "install_state": "testing"}, format="json")
    device.refresh_from_db()
    assert response.status_code == 200
    assert device.software_version == "2.0.0"
    assert device.install_state == "unknown"


def test_release_eligibility_requires_compatible_target_and_newer_version():
    device, _ = device_pair(version="2.0.0", model="M1")
    admin = staff_user(superuser=True)
    newer = SoftwareRelease.objects.create(version="3.0.0", package_url="https://packages.example/3", sha256="a" * 64, compatible_models=["M2"], status="published", target_all_devices=True, created_by=admin, published_at=timezone.now())
    assert available_release_for(device) is None
    newer.compatible_models = ["M1"]
    newer.save(update_fields=["compatible_models"])
    assert available_release_for(device) == newer
    older = SoftwareRelease.objects.create(version="1.0.0", package_url="https://packages.example/1", sha256="b" * 64, status="published", created_by=admin, published_at=timezone.now())
    device.software_version = "1.1.0"
    device.save(update_fields=["software_version"])
    UpdateAssignment.objects.create(release=older, device=device, allow_downgrade=True)
    assert available_release_for(device) == older


def test_archived_inventory_is_hidden_by_default_and_can_be_requested_explicitly():
    admin = staff_user(superuser=True)
    customer = Customer.objects.create(organization_name="Archived Co", contact_name="Mina", contact_phone="555", is_archived=True)
    client = APIClient()
    client.force_authenticate(user=admin)
    assert client.get("/api/v1/customers/").data["count"] == 0
    archived = client.get("/api/v1/customers/?is_archived=true")
    assert archived.data["count"] == 1
    assert archived.data["results"][0]["id"] == customer.pk


def test_archived_customer_events_are_hidden_unless_explicitly_requested():
    device, token = device_pair()
    payload = event_payload()
    device_client(token).post("/api/v1/device/events/", {"events": [payload]}, format="json")
    device.customer.is_archived = True
    device.customer.save(update_fields=["is_archived"])
    admin = staff_user(superuser=True)
    client = APIClient()
    client.force_authenticate(user=admin)
    assert client.get("/api/v1/events/").data["count"] == 0
    assert client.get("/api/v1/events/?device__customer__is_archived=true").data["count"] == 1


def test_super_admin_can_manage_customer_and_device_and_records_audit():
    admin = staff_user(superuser=True)
    client = APIClient()
    client.force_authenticate(user=admin)
    customer_response = client.post("/api/v1/customers/", {
        "organization_name": "  Fleet Co  ", "contact_name": "  Sara  ",
        "contact_email": "  SERVICE@EXAMPLE.TEST  ", "contact_phone": "  123  ", "address": "Depot", "notes": "night shift",
    }, format="json")
    assert customer_response.status_code == 201
    customer = Customer.objects.get(pk=customer_response.data["id"])
    assert customer.contact_email == "service@example.test"
    assert customer.contact_phone == "123"
    device_response = client.post("/api/v1/devices/", {
        "serial_number": "PS-001", "device_model": registration_model(), "customer": customer.pk,
    }, format="json")
    assert device_response.status_code == 201
    assert AuditEntry.objects.filter(action="customer.created").exists()
    assert AuditEntry.objects.filter(action="device.registered").exists()


def test_release_publication_is_atomic_and_assigns_compatible_targets():
    device, _ = device_pair(model="M1")
    other, _ = device_pair(model="M2")
    admin = staff_user(superuser=True)
    client = APIClient()
    client.force_authenticate(user=admin)
    response = client.post("/api/v1/releases/", {
        "version": "3.0.0", "package_url": "https://packages.example/3", "sha256": "a" * 64,
        "compatible_models": ["M1"], "target_all_devices": True, "target_devices": [],
    }, format="json")
    assert response.status_code == 201
    release = SoftwareRelease.objects.get(pk=response.data["id"])
    assert list(release.assignments.values_list("device_id", flat=True)) == [device.pk]
    assert not release.assignments.filter(device=other).exists()
    assert AuditEntry.objects.filter(action="release.published_automatically", target_id=str(release.pk)).exists()


def test_update_result_enforces_safe_lifecycle_and_production_rollout_gate():
    device, token = device_pair()
    admin = staff_user(superuser=True)
    release = SoftwareRelease.objects.create(
        version="2.0.0", package_url="https://packages.example/2", sha256="a" * 64,
        status=SoftwareRelease.Status.PUBLISHED, target_all_devices=True, created_by=admin,
        published_at=timezone.now(),
    )
    assignment = UpdateAssignment.objects.create(release=release, device=device)
    client = device_client(token)
    with override_settings(DEBUG=False, DEVICE_UPDATE_ROLLOUT_ENABLED=False):
        check_in = client.post("/api/v1/device/check-in/", {"install_state": "idle"}, format="json")
        manifest = client.get("/api/v1/device/update-manifest/")
    assert check_in.status_code == 200 and check_in.data["update_available"] is False
    assert manifest.status_code == 200
    assert manifest.data == {"update_available": False, "reason": "release_authenticity_not_verified"}
    invalid_jump = client.post("/api/v1/device/update-result/", {"release_version": release.version, "state": "succeeded"}, format="json")
    assert invalid_jump.status_code == 400
    device.install_state = Device.InstallState.TESTING
    device.save(update_fields=["install_state"])
    assert client.post("/api/v1/device/update-result/", {"release_version": release.version, "state": "downloading"}, format="json").status_code == 200
    assert client.post("/api/v1/device/update-result/", {"release_version": release.version, "state": "downloaded"}, format="json").status_code == 200
    assert client.post("/api/v1/device/update-result/", {"release_version": release.version, "state": "installing"}, format="json").status_code == 400
    device.install_state = Device.InstallState.IDLE
    device.save(update_fields=["install_state"])
    assert client.post("/api/v1/device/update-result/", {"release_version": release.version, "state": "installing"}, format="json").status_code == 200
    assert client.post("/api/v1/device/update-result/", {"release_version": release.version, "state": "succeeded"}, format="json").status_code == 200
    assignment.refresh_from_db()
    assert assignment.state == UpdateAssignment.State.SUCCEEDED
    assert assignment.reported_at is not None


def registration_model():
    from devices.models import DeviceModel
    return DeviceModel.objects.get_or_create(code="AD-UNIT-B", defaults={"display_name": "Unit", "kind": "unit", "edition": "b"})[0].pk
