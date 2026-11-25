import pytest
from rest_framework.test import APIClient

from devices.models import Customer, Device, SoftwareRelease
from .test_api import staff_user
from .test_inventory import admin_client, customer
from .test_customer_membership import portal_user

pytestmark = pytest.mark.django_db


def test_inventory_archive_modes_search_count_pagination_and_legacy_detail():
    owner = customer()
    Device.objects.bulk_create([
        Device(serial_number=f"ARCHIVE-{i:03d}", model_name="Legacy", customer=owner, is_archived=i < 52)
        for i in range(54)
    ])
    client = admin_client()
    assert client.get("/api/v1/devices/").data["count"] == 2
    for mode, expected in [("active", 2), ("archived", 52), ("all", 54)]:
        response = client.get("/api/v1/devices/", {"archive_status": mode, "search": "ARCHIVE", "customer": owner.pk})
        assert response.status_code == 200 and response.data["count"] == expected
        if mode != "all":
            assert all(row["is_archived"] == (mode == "archived") for row in response.data["results"])
    page = client.get("/api/v1/devices/", {"archive_status": "archived", "page": 2, "search": "ARCHIVE"})
    assert page.data["count"] == 52 and len(page.data["results"]) == 2
    assert "archive_status=archived" in page.data["previous"]
    archived = Device.objects.get(serial_number="ARCHIVE-000")
    url = f"/api/v1/devices/{archived.pk}/"
    assert client.get(url).status_code == 404
    assert client.get(url, {"archive_status": "archived"}).status_code == 200
    assert client.get(url, {"is_archived": "true"}).status_code == 200


def test_customer_archive_modes_and_search_are_scoped_before_counting():
    Customer.objects.create(organization_name="Matched active", contact_name="A", is_archived=False)
    Customer.objects.create(organization_name="Matched archived", contact_name="B", is_archived=True)
    Customer.objects.create(organization_name="Other", contact_name="C", is_archived=True)
    client = admin_client()
    for mode, count in [("active", 1), ("archived", 1), ("all", 2)]:
        result = client.get("/api/v1/customers/", {"archive_status": mode, "search": "Matched"})
        assert result.status_code == 200 and result.data["count"] == count


@pytest.mark.parametrize("path", ["/api/v1/devices/", "/api/v1/customers/"])
@pytest.mark.parametrize("params", [{"archive_status": "unknown"}, {"archive_status": ""}, {"archive_status": "all", "is_archived": "false"}])
def test_invalid_archive_filters_do_not_silently_widen_access(path, params):
    assert admin_client().get(path, params).status_code == 400


def test_customer_cannot_use_staff_archive_filters_to_expand_portal_visibility():
    owner = customer()
    foreign = customer()
    own = Device.objects.create(serial_number="OWN", model_name="M", customer=owner)
    Device.objects.create(serial_number="ARCHIVED", model_name="M", customer=owner, is_archived=True)
    Device.objects.create(serial_number="FOREIGN", model_name="M", customer=foreign)
    client = APIClient()
    client.force_authenticate(portal_user(customer=owner))
    for mode in ["active", "archived", "all"]:
        params = {"archive_status": mode, "is_archived": "true"}
        assert client.get("/api/v1/devices/", params).status_code == 403
        assert client.get("/api/v1/customer/devices/", params).status_code == 400
    result = client.get("/api/v1/customer/devices/")
    assert result.data["count"] == 1 and result.data["results"][0]["id"] == own.pk


def test_account_and_release_filters_use_their_own_lifecycle_labels():
    admin = staff_user(superuser=True)
    support = staff_user(support=True)
    support.is_active = False
    support.save()
    portal = portal_user()
    portal.is_active = False
    portal.save()
    client = APIClient()
    client.force_authenticate(admin)
    assert client.get("/api/v1/staff-users/", {"is_active": "false"}).data["results"][0]["id"] == support.pk
    assert client.get("/api/v1/customer-users/", {"is_active": "false"}).data["results"][0]["id"] == portal.pk
    assert client.get("/api/v1/staff-users/", {"is_active": "invalid"}).status_code == 400
    assert client.get("/api/v1/customer-users/", {"is_active": "invalid"}).status_code == 400
    for index, state in enumerate(["draft", "published", "withdrawn"]):
        SoftwareRelease.objects.create(version=f"1.0.{index}", package_url="https://example.test/a.whl", sha256="a" * 64, created_by=admin, status=state)
    result = client.get("/api/v1/releases/", {"status": "withdrawn"})
    assert result.status_code == 200 and result.data["count"] == 1
    assert result.data["results"][0]["status"] == "withdrawn"
    assert client.get("/api/v1/releases/", {"status": "archived"}).status_code == 400
