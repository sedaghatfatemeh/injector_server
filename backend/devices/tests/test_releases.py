from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import close_old_connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from devices.models import AuditEntry, SoftwareRelease, UpdateAssignment
from devices.tests.test_api import device_client, device_pair, staff_user
from devices.views import available_release_for


pytestmark = pytest.mark.django_db


def release_payload(**overrides):
    return {
        "version": "2.0.0", "package_url": "https://packages.example.test/app.zip",
        "sha256": "A" * 64, "compatible_models": ["M1"], "target_all_devices": True,
        **overrides,
    }


def admin_client():
    client = APIClient()
    client.force_authenticate(staff_user(superuser=True))
    return client


def publish(client=None, **overrides):
    response = (client or admin_client()).post("/api/v1/releases/", release_payload(**overrides), format="json")
    assert response.status_code == 201, response.data
    return SoftwareRelease.objects.get(pk=response.data["id"])


@pytest.mark.parametrize("overrides", [
    {"package_url": "http://packages.example.test/app.zip"},
    {"package_url": "https://secret:password@packages.example.test/app.zip"},
    {"package_url": "https://packages.example.test/app.zip#secret"},
    {"sha256": "invalid"}, {"version": "unparseable"}, {"minimum_version": "broken"},
    {"compatible_models": {}}, {"compatible_models": [1]},
    {"target_all_devices": False, "target_devices": []},
])
def test_invalid_release_is_rejected_without_partial_writes(overrides):
    response = admin_client().post("/api/v1/releases/", release_payload(**overrides), format="json")
    assert response.status_code == 400
    assert not SoftwareRelease.objects.exists()
    assert not UpdateAssignment.objects.exists()
    assert not AuditEntry.objects.filter(action="release.published_automatically").exists()


def test_selected_targets_are_atomic_and_exclusive():
    device, _ = device_pair()
    incompatible, _ = device_pair(model="M2")
    client = admin_client()
    for targets, all_devices in [([device.pk], True), ([device.pk, incompatible.pk], False)]:
        response = client.post("/api/v1/releases/", release_payload(
            target_devices=targets, target_all_devices=all_devices,
        ), format="json")
        assert response.status_code == 400
        assert not SoftwareRelease.objects.exists()
    release = publish(client, target_all_devices=False, target_devices=[device.pk])
    assert list(release.assignments.values_list("device_id", flat=True)) == [device.pk]
    assert release.sha256 == "a" * 64
    assert release.status == "published" and release.published_at is not None
    assert client.patch(f"/api/v1/releases/{release.pk}/", {"sha256": "b" * 64}, format="json").status_code == 405
    assert client.delete(f"/api/v1/releases/{release.pk}/").status_code == 405


def test_eligibility_excludes_archived_owners_and_applies_version_constraints():
    eligible, _ = device_pair(version="1.5.0")
    old, _ = device_pair(version="1.0.0")
    newer, _ = device_pair(version="3.0.0")
    archived, _ = device_pair(version="1.5.0")
    archived.customer.is_archived = True
    archived.customer.save()
    release = publish(minimum_version="1.5.0")
    assert list(release.assignments.values_list("device_id", flat=True)) == [eligible.pk]
    assert available_release_for(eligible) == release
    for device in [old, newer, archived]:
        assert available_release_for(device) is None


def test_new_devices_discover_only_all_device_releases_and_withdrawal_stops_delivery():
    original, _ = device_pair()
    client = admin_client()
    selected = publish(client, target_all_devices=False, target_devices=[original.pk])
    new, token = device_pair()
    assert available_release_for(new) is None
    all_devices = publish(client, version="3.0.0")
    with override_settings(DEBUG=True):
        device_client(token).post("/api/v1/device/check-in/", {"install_state": "testing"}, format="json")
        assert device_client(token).get("/api/v1/device/update-manifest/").data["update_available"] is False
        device_client(token).post("/api/v1/device/check-in/", {"install_state": "idle"}, format="json")
        assert device_client(token).get("/api/v1/device/update-manifest/").data["version"] == "3.0.0"
        assert client.post(f"/api/v1/releases/{all_devices.pk}/withdraw/", {}, format="json").status_code == 200
        assert device_client(token).get("/api/v1/device/update-manifest/").data["update_available"] is False
    assert SoftwareRelease.objects.filter(pk=selected.pk).exists()
    assert AuditEntry.objects.filter(action="release.withdrawn", target_id=str(all_devices.pk)).exists()


@pytest.mark.parametrize("device_ids", [[{}], [None], [True], ["garbage"], [], [1, 1]])
def test_invalid_rollback_ids_return_validation_error(device_ids):
    client = admin_client()
    release = publish(client)
    response = client.post(f"/api/v1/releases/{release.pk}/rollback/", {
        "device_ids": device_ids, "reason": "Recovery",
    }, format="json")
    assert response.status_code == 400


def test_rollback_requires_known_newer_version_and_reason_and_resets_report_projection():
    device, _ = device_pair(version="3.0.0")
    unknown, _ = device_pair(version="")
    client = admin_client()
    release = publish(client)
    url = f"/api/v1/releases/{release.pk}/rollback/"
    assert client.post(url, {"device_ids": [unknown.pk], "reason": "Recovery"}, format="json").status_code == 400
    assert client.post(url, {"device_ids": [device.pk], "reason": " "}, format="json").status_code == 400
    assignment = UpdateAssignment.objects.create(
        release=release, device=device, state="failed", reported_at=timezone.now(), result_code="FAILED",
    )
    assert client.post(url, {"device_ids": [device.pk], "reason": "Verified previous release"}, format="json").status_code == 200
    assignment.refresh_from_db()
    assert assignment.allow_downgrade and assignment.state == "available"
    assert assignment.reported_at is None and assignment.result_code == ""
    assert available_release_for(device) == release
    assert AuditEntry.objects.get(action="release.rollback_assigned").details["reason"] == "Verified previous release"


@pytest.mark.parametrize("action", ["publish", "withdraw", "rollback"])
def test_support_cannot_mutate_releases(action):
    release = publish()
    client = APIClient()
    client.force_authenticate(staff_user(support=True))
    url = "/api/v1/releases/" if action == "publish" else f"/api/v1/releases/{release.pk}/{action}/"
    assert client.post(url, release_payload(), format="json").status_code == 403
    assert client.get("/api/v1/releases/").status_code == 200


def test_results_are_idempotent_preserve_timestamps_and_ignore_stale_reports():
    device, token = device_pair()
    release = publish()
    client = device_client(token)
    stamp = timezone.now() - timedelta(hours=2)
    payload = {"release_version": release.version, "state": "downloaded", "result_code": "VERIFIED", "reported_at": stamp.isoformat()}
    url = "/api/v1/device/update-result/"
    assert client.post(url, payload, format="json").data == {"accepted": True}
    assert client.post(url, payload, format="json").data == {"accepted": True, "duplicate": True}
    assert client.post(url, {**payload, "result_code": "CHANGED"}, format="json").status_code == 400
    stale = {**payload, "state": "downloading", "reported_at": (stamp - timedelta(minutes=1)).isoformat()}
    assert client.post(url, stale, format="json").data == {"accepted": True, "stale": True}
    assignment = UpdateAssignment.objects.get(release=release, device=device)
    assert assignment.state == "downloaded" and assignment.reported_at == stamp
    assert assignment.report_received_at > stamp
    assert AuditEntry.objects.filter(action="device.update.downloaded").count() == 1
    assert AuditEntry.objects.filter(action="device.update.stale_report").count() == 1


@pytest.mark.parametrize("extra", [
    {"reported_at": "2026-01-01T10:00:00"},
    {"reported_at": "2099-01-01T10:00:00Z"},
    {"result_code": "Authorization: secret"}, {"result_code": "https://secret.example.test"},
    {"raw_payload": "secret"},
])
def test_result_schema_rejects_unsafe_or_ambiguous_data(extra):
    _, token = device_pair()
    release = publish()
    response = device_client(token).post("/api/v1/device/update-result/", {
        "release_version": release.version, "state": "downloaded", **extra,
    }, format="json")
    assert response.status_code == 400
    assert not AuditEntry.objects.filter(action="device.update.downloaded").exists()


def test_audit_failure_rolls_back_assignment_and_device_version():
    device, token = device_pair()
    release = publish()
    assignment = UpdateAssignment.objects.get(release=release, device=device)
    assignment.state = "installing"
    assignment.save()
    with patch("devices.releases.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            device_client(token).post("/api/v1/device/update-result/", {
                "release_version": release.version, "state": "succeeded",
            }, format="json")
    device.refresh_from_db()
    assignment.refresh_from_db()
    assert assignment.state == "installing" and device.software_version == "1.0.0"


def test_publication_audit_failure_rolls_back_release_targets_and_assignments():
    device, _ = device_pair()
    client = admin_client()
    with patch("devices.views.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post("/api/v1/releases/", release_payload(
                target_all_devices=False, target_devices=[device.pk],
            ), format="json")
    assert not SoftwareRelease.objects.exists()
    assert not UpdateAssignment.objects.exists()


def test_result_rechecks_credential_after_authentication():
    device, token = device_pair()
    release = publish()
    from devices.authentication import issue_device_token
    from devices.releases import record_update_result

    def rotate_then_record(device, credential, data):
        issue_device_token(device)
        return record_update_result(device, credential, data)

    with patch("devices.views.record_update_result", side_effect=rotate_then_record):
        response = device_client(token).post("/api/v1/device/update-result/", {
            "release_version": release.version, "state": "downloaded",
        }, format="json")
    assert response.status_code == 401
    assert UpdateAssignment.objects.get(release=release).state == "available"


def test_delayed_success_does_not_replace_a_newer_check_in_version():
    device, token = device_pair()
    release = publish()
    assignment = UpdateAssignment.objects.get(release=release, device=device)
    assignment.state = "installing"
    assignment.save()
    device.software_version = "3.0.0"
    device.last_seen_at = timezone.now()
    device.save()
    assert device_client(token).post("/api/v1/device/update-result/", {
        "release_version": release.version, "state": "succeeded",
        "reported_at": (timezone.now() - timedelta(days=1)).isoformat(),
    }, format="json").status_code == 200
    device.refresh_from_db()
    assert device.software_version == "3.0.0"


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_results_write_one_audit():
    device, token = device_pair()
    release = publish()
    barrier = Barrier(2)

    def report():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            response = device_client(token).post("/api/v1/device/update-result/", {
                "release_version": release.version, "state": "downloaded", "result_code": "VERIFIED",
            }, format="json")
            return response.status_code, response.data
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: report(), range(2)))
    assert all(status == 200 for status, _ in results)
    assert sum(data.get("duplicate", False) for _, data in results) == 1
    assert AuditEntry.objects.filter(action="device.update.downloaded", target_id=str(device.pk)).count() == 1
