from unittest.mock import patch
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from devices.models import AuditEntry, DeviceCredential, DeviceEvent, SoftwareRelease
from .test_api import device_client, device_pair, staff_user


pytestmark = pytest.mark.django_db
PASSWORD = "Correct-Horse-42!"
SENTINEL = "submitted-secret-must-not-be-audited"


@pytest.fixture(autouse=True)
def clear_throttles():
    cache.clear()


def actor_client(role):
    client = APIClient()
    if role == "anonymous":
        return client
    if role == "device":
        _, token = device_pair()
        return device_client(token)
    user = staff_user(superuser=role in {"super_no_staff", "inactive_super"}, support=role == "support")
    if role in {"ordinary", "super_no_staff"}:
        user.is_staff = False
    if role == "inactive_super":
        user.is_active = False
    user.save()
    client.force_authenticate(user)
    return client


@pytest.mark.parametrize("role", ["anonymous", "device", "ordinary", "unassigned_staff", "super_no_staff", "inactive_super", "support"])
def test_staff_role_matrix_and_denied_mutations_are_audited_without_payloads(role):
    client = actor_client(role)
    owner = staff_user(superuser=True)
    device, _ = device_pair()
    customer = device.customer
    release = SoftwareRelease.objects.create(version="1.0.0", created_by=owner, status="published",
                                              package_url="https://packages.example.test/app.whl", sha256="a" * 64)
    reads = ["customers/", "devices/", "events/", "releases/", "releases/assignments/", "dashboard/summary/", "auth/session/"]
    for path in reads:
        response = client.get("/api/v1/" + path)
        assert response.status_code == (200 if role == "support" else 403), (role, path)
    assert client.get("/api/v1/staff-users/").status_code == 403
    writes = [
        ("post", "customers/"), ("patch", f"customers/{customer.pk}/"), ("put", f"customers/{customer.pk}/"),
        ("delete", f"customers/{customer.pk}/"), ("post", "devices/"), ("patch", f"devices/{device.pk}/"),
        ("put", f"devices/{device.pk}/"), ("delete", f"devices/{device.pk}/"),
        ("post", f"devices/{device.pk}/provision_credential/"), ("post", f"devices/{device.pk}/revoke_credential/"),
        ("post", "releases/"), ("post", f"releases/{release.pk}/withdraw/"), ("post", f"releases/{release.pk}/rollback/"),
        ("post", "staff-users/"),
    ]
    original_digest = DeviceCredential.objects.get(device=device).token_digest
    for method, path in writes:
        response = getattr(client, method)("/api/v1/" + path, {"password": SENTINEL, "credential": SENTINEL}, format="json")
        assert response.status_code == 403, (role, method, path)
    device.refresh_from_db()
    customer.refresh_from_db()
    release.refresh_from_db()
    assert not device.is_archived and not customer.is_archived and release.status == "published"
    assert DeviceCredential.objects.get(device=device).token_digest == original_digest
    denied = AuditEntry.objects.filter(action="authorization.denied")
    assert denied.count() == len(writes) - 1
    assert all(entry.outcome == "denied" for entry in denied)
    assert SENTINEL not in str(list(AuditEntry.objects.values("details", "target_id")))
    if role == "device":
        assert all(entry.actor_id is None for entry in denied)


def test_support_model_permissions_cannot_bypass_api_roles_or_enter_django_admin():
    support = staff_user(support=True)
    support.user_permissions.set(Permission.objects.all())
    api = APIClient()
    api.force_login(support)
    assert api.get("/api/v1/customers/").status_code == 200
    assert api.post("/api/v1/customers/", {}, format="json").status_code == 403
    for path in ("/admin/", "/admin/auth/user/", "/admin/devices/auditentry/"):
        response = api.get(path)
        assert response.status_code == 302 and "/admin/login/" in response["Location"]


def test_denied_target_identifier_is_canonical_and_does_not_echo_untrusted_path():
    client = actor_client("support")
    assert client.post(f"/api/v1/devices/{SENTINEL}/revoke_credential/", {}, format="json").status_code == 403
    audit = AuditEntry.objects.get(action="authorization.denied")
    assert audit.target_id == "" and SENTINEL not in str(audit.details)


def test_active_super_administrator_reads_and_performs_audited_release_actions():
    admin = staff_user(superuser=True)
    device, _ = device_pair(version="2.0.0")
    release = SoftwareRelease.objects.create(version="1.0.0", created_by=admin, status="published",
                                              package_url="https://packages.example.test/app.whl", sha256="a" * 64)
    client = APIClient()
    client.force_login(admin)
    for path in ("/api/v1/staff-users/", "/api/v1/customers/", "/api/v1/releases/", "/admin/devices/auditentry/"):
        assert client.get(path).status_code == 200
    response = client.post(f"/api/v1/releases/{release.pk}/rollback/", {"device_ids": [device.pk], "reason": "Controlled rollback"}, format="json")
    assert response.status_code == 200
    assert AuditEntry.objects.filter(actor=admin, action="release.rollback_assigned").exists()
    assert client.post(f"/api/v1/releases/{release.pk}/withdraw/", {}, format="json").status_code == 200
    assert AuditEntry.objects.filter(actor=admin, action="release.withdrawn").exists()


def test_removing_staff_status_from_a_superuser_revokes_an_existing_session():
    user = staff_user(superuser=True)
    client = APIClient()
    client.force_login(user)
    assert client.get("/api/v1/auth/session/").status_code == 200
    user.is_staff = False
    user.save(update_fields=["is_staff"])
    assert client.get("/api/v1/auth/session/").status_code == 403
    assert client.get("/api/v1/staff-users/").status_code == 403
    assert client.post("/api/v1/customers/", {}, format="json").status_code == 403


@pytest.mark.parametrize("role", ["support", "unassigned_staff", "super_no_staff", "inactive_super"])
def test_native_admin_login_rejects_nonadministrators_with_correct_password(role):
    user = staff_user(superuser=role in {"super_no_staff", "inactive_super"}, support=role == "support")
    if role == "super_no_staff":
        user.is_staff = False
    elif role == "inactive_super":
        user.is_active = False
    user.save()
    client = Client()
    response = client.post("/admin/login/", {"username": user.username, "password": PASSWORD})
    assert response.status_code == 200
    assert client.get("/api/v1/auth/session/").status_code == 403
    entry = AuditEntry.objects.get(action="staff.sign_in_failed")
    assert entry.details == {"source": "django_admin"} and entry.actor_id is None
    assert PASSWORD not in str(entry.details)


def test_native_admin_login_is_csrf_protected_and_audited():
    user = staff_user(superuser=True)
    client = Client(enforce_csrf_checks=True)
    data = {"username": user.username, "password": PASSWORD}
    assert client.post("/admin/login/", data).status_code == 403
    client.get("/admin/login/")
    response = client.post("/admin/login/", {**data, "csrfmiddlewaretoken": client.cookies["csrftoken"].value})
    assert response.status_code == 302
    assert client.get("/admin/").status_code == 200
    audit = AuditEntry.objects.get(action="staff.signed_in")
    assert audit.actor == user and audit.details == {"source": "django_admin"}


def test_native_admin_and_console_share_login_attempt_limit(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "2/minute",
    }}
    client = Client()
    assert client.post("/admin/login/", {}).status_code == 200
    assert client.post("/api/v1/auth/login/", {}, content_type="application/json").status_code == 403
    response = client.post("/admin/login/", {})
    assert response.status_code == 429 and int(response["Retry-After"]) > 0
    assert "no-store" in response["Cache-Control"]


def test_admin_audit_failure_cannot_create_a_session():
    user = staff_user(superuser=True)
    client = Client()
    with patch("devices.admin_site.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post("/admin/login/", {"username": user.username, "password": PASSWORD})
    assert client.get("/api/v1/auth/session/").status_code == 403


def test_native_admin_logout_requires_csrf_revokes_session_and_audits():
    user = staff_user(superuser=True)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post("/admin/logout/", {}).status_code == 403
    client.get("/admin/")
    response = client.post("/admin/logout/", {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
    assert response.status_code == 200
    assert client.get("/api/v1/auth/session/").status_code == 403
    entry = AuditEntry.objects.get(action="staff.signed_out")
    assert entry.actor == user and entry.details == {"source": "django_admin"}


def test_native_admin_logout_audit_failure_preserves_the_original_session():
    client = Client()
    client.force_login(staff_user(superuser=True))
    with patch("devices.admin_site.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post("/admin/logout/", {})
    assert client.get("/api/v1/auth/session/").status_code == 200


def test_native_admin_staff_account_changes_are_audited_without_passwords():
    admin = staff_user(superuser=True)
    client = Client()
    client.force_login(admin)
    name = "native-created-user"
    response = client.post("/admin/auth/user/add/", {"username": name, "usable_password": "true",
                           "password1": PASSWORD, "password2": PASSWORD, "_save": "Save"})
    assert response.status_code == 302, response.context["adminform"].form.errors if response.status_code == 200 else response.status_code
    target = get_user_model().objects.get(username=name)
    target_id = str(target.pk)
    assert target.check_password(PASSWORD)
    assert AuditEntry.objects.filter(actor=admin, action="staff.created", target_id=target_id).exists()
    group = Group.objects.get_or_create(name="support")[0]
    response = client.post(f"/admin/auth/user/{target.pk}/change/", {"username": name, "email": "native@example.test",
                           "is_active": "on", "is_staff": "on", "groups": [group.pk],
                           "date_joined_0": target.date_joined.strftime("%Y-%m-%d"),
                           "date_joined_1": target.date_joined.strftime("%H:%M:%S"), "_save": "Save"})
    assert response.status_code == 302, response.context["adminform"].form.errors if response.status_code == 200 else response.status_code
    assert AuditEntry.objects.filter(actor=admin, action="staff.updated", target_id=target_id).exists()
    assert client.post(f"/admin/auth/user/{target.pk}/delete/", {"post": "yes"}).status_code == 302
    assert not get_user_model().objects.filter(pk=target.pk).exists()
    deleted = AuditEntry.objects.get(action="staff.deleted", target_id=target_id)
    assert deleted.details["actor_user_id"] == str(admin.pk)
    assert PASSWORD not in str(list(AuditEntry.objects.values("details")))


def test_native_admin_user_creation_rolls_back_when_audit_fails():
    client = Client()
    client.force_login(staff_user(superuser=True))
    with patch("devices.admin.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post("/admin/auth/user/add/", {"username": "unaudited-user", "usable_password": "true",
                        "password1": PASSWORD, "password2": PASSWORD, "_save": "Save"})
    assert not get_user_model().objects.filter(username="unaudited-user").exists()


def test_bulk_account_delete_and_its_audits_roll_back_together():
    client = Client()
    client.force_login(staff_user(superuser=True))
    targets = [staff_user(support=True), staff_user(support=True)]
    original_create = AuditEntry.objects.create
    recorded = 0

    def fail_second_audit(**kwargs):
        nonlocal recorded
        if kwargs.get("action") == "staff.deleted":
            recorded += 1
            if recorded == 2:
                raise RuntimeError("audit unavailable")
        return original_create(**kwargs)

    with patch("devices.admin.AuditEntry.objects.create", side_effect=fail_second_audit):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            client.post("/admin/auth/user/", {"action": "delete_selected", "_selected_action": [user.pk for user in targets],
                        "post": "yes", "index": "0"})
    assert get_user_model().objects.filter(pk__in=[user.pk for user in targets]).count() == 2
    assert not AuditEntry.objects.filter(action="staff.deleted").exists()


def test_device_events_and_audits_remain_readonly_in_native_admin():
    device, _ = device_pair()
    event = DeviceEvent.objects.create(device=device, event_id=uuid.uuid4(), code="STATUS", occurred_at=timezone.now())
    client = Client()
    client.force_login(staff_user(superuser=True))
    assert client.get(f"/admin/devices/deviceevent/{event.pk}/change/").status_code == 200
    for path in ("/admin/devices/deviceevent/add/", f"/admin/devices/deviceevent/{event.pk}/delete/"):
        assert client.get(path).status_code == 403
    assert client.post(f"/admin/devices/deviceevent/{event.pk}/change/", {"summary": "tamper"}).status_code == 403
    assert client.post("/admin/devices/deviceevent/", {"action": "delete_selected", "_selected_action": [event.pk], "post": "yes"}).status_code == 200
    assert DeviceEvent.objects.filter(pk=event.pk).exists()
    audit = AuditEntry.objects.first()
    assert client.post(f"/admin/devices/auditentry/{audit.pk}/delete/", {"post": "yes"}).status_code == 403
