from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.cache import cache
from rest_framework.test import APIClient

from devices.models import AuditEntry, Customer, CustomerMembership
from .test_customer_membership import portal_user
from .test_staff_auth import sign_in

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reset_throttle_cache():
    cache.clear()


def test_customer_secure_session_restore_logout_and_audit():
    user = portal_user()
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
    assert client.post("/api/v1/auth/login/", {"email": user.email, "password": "Correct-Horse-42!"}).status_code == 403
    result = sign_in(client, user)
    assert result.status_code == 200
    assert result.data["role"] == "customer" and "no-store" in result["Cache-Control"]
    assert result.data["organization"] == {"id": user.customer_membership.customer_id, "name": "Workshop"}
    assert "password" not in str(result.data)
    assert client.cookies["sessionid"]["httponly"] and client.cookies["sessionid"]["samesite"] == "Lax"
    assert client.cookies["csrftoken"].value != token
    session_key = client.cookies["sessionid"].value
    assert client.get("/api/v1/auth/session/").data["role"] == "customer"
    token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
    assert client.post("/api/v1/auth/logout/", {}, HTTP_X_CSRFTOKEN=token).status_code == 204
    assert not Session.objects.filter(session_key=session_key).exists()
    assert client.get("/api/v1/auth/session/").status_code == 403
    assert AuditEntry.objects.filter(actor=user, action="customer.signed_in").count() == 1
    assert AuditEntry.objects.filter(actor=user, action="customer.signed_out").count() == 1


@pytest.mark.parametrize("kind", ["password", "inactive", "missing", "archived", "staff", "superuser", "support", "ambiguous"])
def test_customer_credential_denial_remains_generic(kind):
    user = portal_user()
    if kind == "missing":
        CustomerMembership.objects.filter(user=user).delete()
    elif kind == "archived":
        Customer.objects.filter(pk=user.customer_membership.customer_id).update(is_archived=True)
    elif kind == "support":
        user.groups.add(Group.objects.get_or_create(name="support")[0])
    elif kind == "ambiguous":
        get_user_model().objects.create_user(username="duplicate", email=user.email.upper(), password="Unrelated-Password-73!")
    elif kind == "password":
        user.set_password("Different-Password-73!")
        user.save()
    else:
        setattr(user, {"inactive": "is_active", "staff": "is_staff", "superuser": "is_superuser"}[kind], kind != "inactive")
        user.save()
    client = APIClient(enforce_csrf_checks=True)
    result = sign_in(client, user)
    assert result.status_code == 403 and str(result.data["detail"]) == "Email or password is incorrect."
    assert "sessionid" not in client.cookies
    assert user.email not in str(AuditEntry.objects.last().details)


@pytest.mark.parametrize("kind", ["expired", "inactive", "missing", "archived", "staff", "password"])
def test_existing_customer_session_loses_access_on_next_request(kind):
    user = portal_user()
    client = APIClient()
    assert sign_in(client, user).status_code == 200
    if kind == "expired":
        session = client.session
        session.set_expiry(-1)
        session.save()
    elif kind == "missing":
        CustomerMembership.objects.filter(user=user).delete()
    elif kind == "archived":
        Customer.objects.filter(pk=user.customer_membership.customer_id).update(is_archived=True)
    elif kind == "password":
        user.set_password("New-Password-97!")
        user.save()
    else:
        setattr(user, "is_active" if kind == "inactive" else "is_staff", kind != "inactive")
        user.save()
    assert client.get("/api/v1/auth/session/").status_code == 403


def test_customer_browser_credentials_cannot_reach_staff_admin_or_device_endpoints():
    user = portal_user()
    client = APIClient()
    assert sign_in(client, user).status_code == 200
    for path in ["devices/", "customers/", "events/", "releases/", "staff-users/", "dashboard/summary/"]:
        assert client.get(f"/api/v1/{path}").status_code == 403
        assert client.post(f"/api/v1/{path}", {}, format="json").status_code in {403, 405}
    assert client.get("/admin/").status_code == 302
    assert client.post("/api/v1/device/check-in/", {}, format="json").status_code == 401
    assert client.get("/api/v1/device/update-manifest/").status_code == 401


def test_customer_login_limit_and_atomic_audit_failure(settings):
    user = portal_user()
    client = APIClient()
    with patch("devices.views.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            sign_in(client, user)
    assert not Session.objects.exists()
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "1/minute"}}
    # The audit-failed attempt already spent an attempt in the shared limiter.
    assert sign_in(client, user).status_code == 429
