"""Exercise collected admin assets through middleware, without runserver or a database."""
from html.parser import HTMLParser

import pytest
from django.core.management import call_command
from django.test import Client


class StaticReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value and value.startswith("/static/"):
                self.urls.add(value)


@pytest.mark.parametrize("debug", [False, True])
def test_admin_assets_are_served_without_runserver(settings, tmp_path, debug):
    settings.DEBUG = debug
    settings.SECURE_SSL_REDIRECT = False
    settings.STATIC_ROOT = tmp_path / "collected"
    settings.WHITENOISE_AUTOREFRESH = False
    settings.WHITENOISE_USE_FINDERS = False
    call_command("collectstatic", interactive=False, verbosity=0)
    client = Client()
    login = client.get("/admin/login/")
    assert login.status_code == 200
    references = StaticReferences()
    references.feed(login.content.decode())
    assert any("base." in url and url.endswith(".css") for url in references.urls)
    assert any(url.endswith(".js") for url in references.urls)
    for url in references.urls:
        response = client.get(url)
        assert response.status_code == 200, url
        content = b"".join(response.streaming_content)
        assert content
        if url.endswith(".css"):
            assert response["Content-Type"].startswith("text/css")
        elif url.endswith(".js"):
            assert "javascript" in response["Content-Type"]
        response.close()
    base_css = client.get("/static/admin/css/base.css", HTTP_ACCEPT_ENCODING="gzip")
    assert base_css.status_code == 200
    assert base_css["Content-Encoding"] == "gzip"
    base_css.close()
    assert client.get("/static/admin/css/missing.css").status_code == 404
    assert client.get("/static/../config/settings.py").status_code == 404
