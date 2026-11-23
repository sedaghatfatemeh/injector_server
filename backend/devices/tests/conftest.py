"""Prepare production-style admin assets once, without writing into the checkout."""
import pytest
from django.core.management import call_command
from django.test import override_settings


@pytest.fixture(scope="session", autouse=True)
def collected_admin_assets(django_test_environment, tmp_path_factory):
    with override_settings(STATIC_ROOT=tmp_path_factory.mktemp("admin-static")):
        call_command("collectstatic", interactive=False, verbosity=0)
        yield
