import runpy
from pathlib import Path

import pytest
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, override_settings


@pytest.mark.parametrize("trust_proxy", [None, "false", "true"])
@pytest.mark.parametrize("scheme", ["http", "https"])
def test_proxy_https_requires_explicit_trust(monkeypatch, trust_proxy, scheme):
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-private-settings-key")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "example.com")
    monkeypatch.delenv("DJANGO_TRUST_PROXY_HTTPS", raising=False)
    if trust_proxy is not None:
        monkeypatch.setenv("DJANGO_TRUST_PROXY_HTTPS", trust_proxy)
    config = runpy.run_path(str(Path(__file__).resolve().parents[2] / "config" / "settings.py"))
    assert config["SESSION_COOKIE_SECURE"]
    assert config["CSRF_COOKIE_SECURE"]
    with override_settings(
        ALLOWED_HOSTS=["example.com"],
        SECURE_SSL_REDIRECT=config["SECURE_SSL_REDIRECT"],
        SECURE_PROXY_SSL_HEADER=config.get("SECURE_PROXY_SSL_HEADER"),
    ):
        request = RequestFactory().get(
            "/health/live/", HTTP_HOST="example.com", HTTP_X_FORWARDED_PROTO=scheme
        )
        response = SecurityMiddleware(lambda request: HttpResponse("ok"))(request)
    if trust_proxy == "true" and scheme == "https":
        assert response.status_code == 200
    else:
        assert response.status_code == 301
        assert response["Location"] == "https://example.com/health/live/"
