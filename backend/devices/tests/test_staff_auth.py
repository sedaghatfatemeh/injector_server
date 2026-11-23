from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.management import call_command
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from devices.models import AuditEntry, StaffLoginThrottleBucket
from .test_api import staff_user


pytestmark = pytest.mark.django_db
LOGIN = "/api/v1/auth/login/"
PASSWORD = "Correct-Horse-42!"


@pytest.fixture(autouse=True)
def reset_cache():
    cache.clear()


@pytest.fixture
def limited_login(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "2/minute"},
        "NUM_PROXIES": 0,
    }


def sign_in(client, user, **headers):
    token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
    return client.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token, **headers)


@pytest.mark.parametrize("kind", ["wrong_password", "missing", "inactive", "nonstaff", "missing_role", "ambiguous_email"])
def test_denied_credentials_have_generic_response_and_secret_free_audit(kind):
    user = staff_user(support=True)
    email, password = user.email, PASSWORD
    if kind == "wrong_password":
        password = "Incorrect-Password-43!"
    elif kind == "missing":
        email = "unknown@example.test"
    elif kind == "inactive":
        user.is_active = False
        user.save(update_fields=["is_active"])
    elif kind == "nonstaff":
        user.is_staff = False
        user.save(update_fields=["is_staff"])
    elif kind == "missing_role":
        user.groups.clear()
    elif kind == "ambiguous_email":
        get_user_model().objects.create_user(username="duplicate", email=user.email.upper(), password=PASSWORD)
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
    response = client.post(LOGIN, {"email": email, "password": password}, format="json", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 403
    assert str(response.data["detail"]) == "Email or password is incorrect."
    assert client.get("/api/v1/auth/session/").status_code == 403
    entry = AuditEntry.objects.get(action="staff.sign_in_failed")
    assert entry.outcome == "denied" and entry.actor_id is None
    assert email not in str(entry.details) and password not in str(entry.details)
    assert "sessionid" not in client.cookies


def test_login_requires_csrf_and_rejects_untrusted_origin(settings):
    settings.CSRF_TRUSTED_ORIGINS = ["https://console.example.test"]
    user = staff_user(superuser=True)
    client = APIClient(enforce_csrf_checks=True)
    data = {"email": user.email, "password": PASSWORD}
    assert client.post(LOGIN, data, format="json").status_code == 403
    token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
    assert client.post(LOGIN, data, format="json", HTTP_X_CSRFTOKEN=token,
                       HTTP_ORIGIN="https://untrusted.example.test").status_code == 403
    assert sign_in(client, user, HTTP_ORIGIN="https://console.example.test").status_code == 200


def test_login_rotates_session_and_csrf_and_restores_staff_identity(settings):
    settings.STAFF_SESSION_AGE_SECONDS = 3600
    user = staff_user(superuser=True)
    client = APIClient(enforce_csrf_checks=True)
    initial_session = client.session
    initial_session["before_login"] = True
    initial_session.save()
    old_key = initial_session.session_key
    client.get("/api/v1/auth/csrf/")
    old_csrf = client.cookies["csrftoken"].value
    response = sign_in(client, user)
    assert response.status_code == 200
    assert set(response.data) == {"authenticated", "email", "role"}
    assert client.session.session_key != old_key
    assert not Session.objects.filter(session_key=old_key).exists()
    assert client.cookies["csrftoken"].value != old_csrf
    assert client.cookies["sessionid"]["httponly"]
    assert client.cookies["sessionid"]["samesite"] == "Lax"
    assert client.session.get_expiry_age() == 3600
    restored = client.get("/api/v1/auth/session/")
    assert restored.status_code == 200 and restored.data == {"email": user.email, "role": "super_admin"}


def test_logout_requires_csrf_and_revokes_server_session():
    user = staff_user(support=True)
    client = APIClient(enforce_csrf_checks=True)
    assert sign_in(client, user).status_code == 200
    session_key = client.session.session_key
    assert client.post("/api/v1/auth/logout/", {}, format="json").status_code == 403
    assert client.get("/api/v1/auth/session/").status_code == 200
    response = client.post("/api/v1/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert response.status_code == 204
    assert not Session.objects.filter(session_key=session_key).exists()
    assert client.get("/api/v1/auth/session/").status_code == 403
    assert AuditEntry.objects.filter(actor=user, action="staff.signed_out").exists()


@pytest.mark.parametrize("change", ["expired", "inactive", "password_changed"])
def test_expiry_and_account_security_changes_remove_session_access(change):
    user = staff_user(support=True)
    client = APIClient(enforce_csrf_checks=True)
    assert sign_in(client, user).status_code == 200
    if change == "expired":
        session = client.session
        session.set_expiry(-1)
        session.save()
    elif change == "inactive":
        user.is_active = False
        user.save(update_fields=["is_active"])
    else:
        user.set_password("Changed-Password-76!")
        user.save(update_fields=["password"])
    assert client.get("/api/v1/auth/session/").status_code == 403
    assert client.get("/api/v1/customers/").status_code == 403


def test_login_audit_failure_cannot_establish_a_session():
    user = staff_user(superuser=True)
    client = APIClient(enforce_csrf_checks=True)
    with patch("devices.views.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError, match="audit unavailable"):
            sign_in(client, user)
    assert "sessionid" not in client.cookies
    assert client.get("/api/v1/auth/session/").status_code == 403


def test_login_limits_apply_to_authenticated_users_and_ignore_spoofed_forwarding(limited_login):
    client = APIClient()
    client.force_login(staff_user(support=True))
    for _ in range(2):
        assert client.post(LOGIN, {}, format="json").status_code == 403
    rejected = client.post(LOGIN, {}, format="json", HTTP_X_FORWARDED_FOR="203.0.113.44")
    assert rejected.status_code == 429 and 1 <= int(rejected["Retry-After"]) <= 60
    assert APIClient().post(LOGIN, {}, format="json").status_code == 429
    assert APIClient().post(LOGIN, {}, format="json", REMOTE_ADDR="198.51.100.17").status_code == 403
    assert StaffLoginThrottleBucket.objects.count() == 2
    assert all(len(key) == 64 for key in StaffLoginThrottleBucket.objects.values_list("key", flat=True))
    assert AuditEntry.objects.filter(action="staff.sign_in_throttled", outcome="denied").count() == 2


def test_expired_login_window_allows_new_attempts(limited_login):
    client = APIClient()
    now = timezone.now()
    with patch("devices.views.timezone.now", return_value=now):
        assert client.post(LOGIN, {}, format="json").status_code == 403
        assert client.post(LOGIN, {}, format="json").status_code == 403
        assert client.post(LOGIN, {}, format="json").status_code == 429
    with patch("devices.views.timezone.now", return_value=now + timedelta(seconds=61)):
        assert client.post(LOGIN, {}, format="json").status_code == 403
    assert StaffLoginThrottleBucket.objects.get().attempt_count == 1


def test_pruning_login_counters_keeps_current_windows():
    now = timezone.now()
    StaffLoginThrottleBucket.objects.create(key="a" * 64, window_started_at=now - timedelta(days=8), attempt_count=10)
    recent = StaffLoginThrottleBucket.objects.create(key="b" * 64, window_started_at=now, attempt_count=10)
    call_command("prune_login_throttles")
    assert list(StaffLoginThrottleBucket.objects.values_list("pk", flat=True)) == [recent.pk]


@pytest.mark.django_db(transaction=True)
def test_login_limit_is_shared_and_serialized_across_database_connections(limited_login, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "1/minute"},
    }
    barrier = Barrier(3)

    def attempt(_):
        try:
            client = APIClient()
            barrier.wait(timeout=10)
            return client.post(LOGIN, {}, format="json").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=3) as executor:
        responses = list(executor.map(attempt, range(3)))
    assert sorted(responses) == [403, 429, 429]
    assert StaffLoginThrottleBucket.objects.get().attempt_count == 1
