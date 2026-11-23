from io import StringIO
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework.test import APIClient

from devices.authentication import digest_device_token, issue_device_token, revoke_device_token
from devices.models import AuditEntry, Device, DeviceCredential
from devices.serializers import CheckInSerializer
from .test_api import device_client, device_pair, staff_user


pytestmark = pytest.mark.django_db
CHECK_IN = "/api/v1/device/check-in/"


@pytest.fixture(autouse=True)
def clear_throttles():
    cache.clear()


def test_heartbeat_preserves_reported_state_and_only_updates_authenticated_device():
    device, token = device_pair(version="2.4.1")
    other, _ = device_pair()
    device.install_state = "testing"
    device.save(update_fields=["install_state"])
    before = timezone.now()
    response = device_client(token).post(CHECK_IN, {}, format="json")
    assert response.status_code == 200 and response.data["accepted"]
    device.refresh_from_db()
    other.refresh_from_db()
    assert device.software_version == "2.4.1" and device.install_state == "testing"
    assert before <= device.last_seen_at == response.data["server_time"] <= timezone.now()
    assert other.last_seen_at is None


def test_partial_check_in_preserves_omitted_fields_and_explicit_unknowns_are_recorded():
    device, token = device_pair(version="1.0.0")
    client = device_client(token)
    assert client.post(CHECK_IN, {"install_state": "testing"}, format="json").status_code == 200
    device.refresh_from_db()
    assert device.software_version == "1.0.0" and device.install_state == "testing"
    assert client.post(CHECK_IN, {"software_version": "1.1.0"}, format="json").status_code == 200
    device.refresh_from_db()
    assert device.software_version == "1.1.0" and device.install_state == "testing"
    assert client.post(CHECK_IN, {"software_version": "", "install_state": "unknown"}, format="json").status_code == 200
    device.refresh_from_db()
    assert device.software_version == "" and device.install_state == "unknown"


@pytest.mark.parametrize("payload", [
    {"device": 999}, {"serial_number": "OTHER"}, {"last_seen_at": "2099-01-01T00:00:00Z"},
    {"install_state": "running"}, {"install_state": None}, {"software_version": None},
    {"software_version": 12}, {"software_version": "a" * 81}, [], "invalid", 12,
])
def test_invalid_check_in_cannot_change_device_or_freshness(payload):
    device, token = device_pair(version="2.0.0")
    response = device_client(token).post(CHECK_IN, payload, format="json")
    assert response.status_code == 400
    device.refresh_from_db()
    assert device.software_version == "2.0.0" and device.last_seen_at is None


@pytest.mark.parametrize("body,content_type,status", [
    (b"{", "application/json", 400),
    (b'{"software_version":"\xff"}', "application/json", 400),
    (b'{"install_state":"\\ud800"}', "application/json", 400),
    (b'{"\\ud800":true}', "application/json", 400),
    ("{}".encode("utf-16"), "application/json; charset=utf-16", 400),
    (b"[" * 1200 + b"]" * 1200, "application/json", 400),
    (b"install_state=idle", "application/x-www-form-urlencoded", 415),
    (b" " * 4097 + b"{}", "application/json", 413),
])
def test_malformed_or_oversized_check_in_is_rejected_without_checking_in(body, content_type, status):
    device, token = device_pair()
    response = device_client(token).generic("POST", CHECK_IN, body, content_type=content_type)
    assert response.status_code == status
    device.refresh_from_db()
    assert device.last_seen_at is None


def test_check_in_body_limit_is_configurable(settings):
    settings.DEVICE_CHECK_IN_MAX_BYTES = 2
    _, token = device_pair()
    client = device_client(token)
    assert client.generic("POST", CHECK_IN, b"{}", content_type="application/json").status_code == 200
    assert client.generic("POST", CHECK_IN, b" {}", content_type="application/json").status_code == 413


@pytest.mark.parametrize("header", ["", "Device", "Device a b", "Bearer invalid", "Device " + "a" * 513,
                                         b"Device \xff", "Device \u2603"])
def test_bad_device_credentials_fail_generically_without_mutations(header):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=header)
    response = client.post(CHECK_IN, {}, format="json")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Device"
    assert not Device.objects.filter(last_seen_at__isnull=False).exists()


@pytest.mark.parametrize("change", ["revoked", "rotated", "archived"])
def test_check_in_revalidates_identity_after_authentication_before_writing(change):
    device, token = device_pair()
    original = CheckInSerializer.is_valid

    def validate_then_change(serializer, *args, **kwargs):
        result = original(serializer, *args, **kwargs)
        if change == "revoked":
            revoke_device_token(device)
        elif change == "rotated":
            issue_device_token(device)
        else:
            Device.objects.filter(pk=device.pk).update(is_archived=True)
        return result

    with patch.object(CheckInSerializer, "is_valid", validate_then_change):
        response = device_client(token).post(CHECK_IN, {"software_version": "9.0.0"}, format="json")
    assert response.status_code == 401
    device.refresh_from_db()
    assert device.last_seen_at is None and device.software_version == "1.0.0"


def test_rotation_and_revocation_are_atomic_with_auditing():
    device, token = device_pair()
    original_digest = DeviceCredential.objects.get(device=device).token_digest
    with patch("devices.authentication.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            issue_device_token(device)
        with pytest.raises(RuntimeError, match="audit unavailable"):
            revoke_device_token(device)
    credential = DeviceCredential.objects.get(device=device)
    assert credential.token_digest == original_digest and credential.revoked_at is None
    assert device_client(token).post(CHECK_IN, {}, format="json").status_code == 200


def test_cli_provision_revoke_and_rotate_show_secrets_once_and_audit_without_secrets():
    device, original = device_pair()
    out = StringIO()
    call_command("provision_device", device.serial_number, stdout=out, no_color=True)
    token = out.getvalue().splitlines()[-1]
    assert out.getvalue().count(token) == 1 and token != original
    assert DeviceCredential.objects.get(device=device).token_digest == digest_device_token(token)
    assert device_client(original).post(CHECK_IN, {}, format="json").status_code == 401
    assert device_client(token).post(CHECK_IN, {}, format="json").status_code == 200
    call_command("revoke_device_credential", device.serial_number, stdout=StringIO())
    assert device_client(token).post(CHECK_IN, {}, format="json").status_code == 401
    call_command("revoke_device_credential", device.serial_number, stdout=StringIO())
    assert AuditEntry.objects.filter(action="device.credential_revoked").count() == 1
    out = StringIO()
    call_command("provision_device", device.serial_number, stdout=out, no_color=True)
    replacement = out.getvalue().splitlines()[-1]
    assert replacement != token and device_client(replacement).post(CHECK_IN, {}, format="json").status_code == 200
    audits = str(list(AuditEntry.objects.values("action", "details")))
    assert all(secret not in audits for secret in (original, token, replacement))
    assert AuditEntry.objects.filter(action="device.credential_rotated", details__source="management_command").count() == 2


def test_cli_audit_failure_does_not_rotate_or_print_a_credential():
    device, token = device_pair()
    out = StringIO()
    with patch("devices.authentication.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            call_command("provision_device", device.serial_number, stdout=out)
    assert out.getvalue() == ""
    assert device_client(token).post(CHECK_IN, {}, format="json").status_code == 200


def test_archived_device_cannot_be_provisioned_or_check_in_but_can_be_revoked():
    device, token = device_pair()
    device.is_archived = True
    device.save(update_fields=["is_archived"])
    with pytest.raises(ValueError, match="archived"):
        issue_device_token(device)
    with pytest.raises(CommandError, match="No active device"):
        call_command("provision_device", device.serial_number, stdout=StringIO())
    assert device_client(token).post(CHECK_IN, {}, format="json").status_code == 401
    call_command("revoke_device_credential", device.serial_number, stdout=StringIO())
    assert DeviceCredential.objects.get(device=device).revoked_at is not None


def test_staff_api_provision_and_revoke_are_admin_only_and_secret_cannot_be_retrieved():
    device, old = device_pair()
    client = APIClient()
    admin = staff_user(superuser=True)
    client.force_authenticate(admin)
    url = f"/api/v1/devices/{device.pk}/"
    response = client.post(url + "provision_credential/", {}, format="json")
    assert response.status_code == 201 and response["Cache-Control"] == "no-store"
    token = response.data["credential"]
    assert response.data["shown_once"] is True
    assert token not in str(client.get(url).data)
    assert digest_device_token(token) not in str(client.get(url).data)
    assert device_client(old).post(CHECK_IN, {}, format="json").status_code == 401
    assert client.post(url + "revoke_credential/", {}, format="json").data == {"revoked": True, "changed": True}
    assert client.post(url + "revoke_credential/", {}, format="json").data == {"revoked": True, "changed": False}
    assert device_client(token).post(CHECK_IN, {}, format="json").status_code == 401
    entry = AuditEntry.objects.get(action="device.credential_revoked")
    assert entry.actor == admin and token not in str(entry.details)
    client.force_authenticate(staff_user(support=True))
    for action in ("provision_credential/", "revoke_credential/"):
        assert client.post(url + action, {}, format="json").status_code == 403


def test_device_rate_allowances_are_separate_per_device_and_endpoint(settings):
    scopes = ("device_check_in", "device_events", "device_manifest", "device_update_result")
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **{scope: "1/minute" for scope in scopes},
    }}
    _, first_token = device_pair()
    _, second_token = device_pair()
    first, second = device_client(first_token), device_client(second_token)
    for path, method, expected in ((CHECK_IN, "post", 200), ("/api/v1/device/events/", "post", 400),
                                   ("/api/v1/device/update-manifest/", "get", 200), ("/api/v1/device/update-result/", "post", 400)):
        args = (path,) if method == "get" else (path, {})
        assert getattr(first, method)(*args, format="json").status_code == expected
        limited = getattr(first, method)(*args, format="json")
        assert limited.status_code == 429 and "Retry-After" in limited
        assert getattr(second, method)(*args, format="json").status_code == expected
