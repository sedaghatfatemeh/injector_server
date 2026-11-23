import pytest
from django.core.management import call_command


@pytest.fixture
def console_assets(tmp_path, settings):
    frontend = tmp_path / "console"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<html lang="fa" dir="rtl"><script src="/static/console/assets/app.js"></script></html>',
        encoding="utf-8",
    )
    (frontend / "assets" / "app.js").write_text('console.log("console");', encoding="utf-8")
    settings.FRONTEND_DIST = frontend
    settings.STATICFILES_DIRS = [("console", frontend)]
    settings.STATIC_ROOT = tmp_path / "collected"
    settings.DEBUG = False
    settings.SECURE_SSL_REDIRECT = False
    call_command("collectstatic", interactive=False, verbosity=0)


@pytest.mark.parametrize("path", ["/", "/customer/devices", "/customer/devices/7/"])
def test_console_shell_without_authenticated_data(client, console_assets, path):
    response = client.get(path)
    assert response.status_code == 200
    assert b'dir="rtl"' in b"".join(response.streaming_content)
    assert "no-store" in response["Cache-Control"]
    assert "sessionid" not in response.cookies
    assert client.head(path).status_code == 200
    assert client.post(path).status_code == 405


def test_collected_console_assets_are_served_in_production(client, console_assets):
    response = client.get("/static/console/assets/app.js")
    assert response.status_code == 200
    assert b'console.log("console");' == b"".join(response.streaming_content)


def test_console_does_not_mask_unknown_api_or_device_paths(client, console_assets):
    assert client.get("/api/v1/nonexistent/").status_code == 404
    assert client.get("/customer/devices/not-an-id").status_code == 404


def test_unbuilt_console_returns_404(client, settings, tmp_path):
    settings.FRONTEND_DIST = tmp_path / "absent"
    assert client.get("/").status_code == 404
