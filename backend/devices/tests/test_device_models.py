from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from devices.models import AuditEntry, Device, DeviceModel
from .test_api import device_pair, staff_user
from .test_inventory import admin_client, customer

pytestmark = pytest.mark.django_db


def catalog_model(code="AD-UNIT-B", **kwargs):
    return DeviceModel.objects.get_or_create(code=code, defaults={
        "display_name": code, "kind": "unit", "edition": "b", **kwargs,
    })[0]


def test_admin_creates_model_and_audit_is_atomic():
    client = admin_client()
    data = {"code": "ad-unit-x", "display_name": "Special unit", "kind": "unit", "edition": "pc"}
    result = client.post("/api/v1/device-models/", data, format="json")
    assert result.status_code == 201 and result.data["code"] == "AD-UNIT-X"
    assert AuditEntry.objects.filter(action="device_model.created", target_id=str(result.data["id"])).exists()
    assert client.post("/api/v1/device-models/", data, format="json").status_code == 400
    with patch.object(AuditEntry.objects, "create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            client.post("/api/v1/device-models/", {**data, "code": "AD-UNIT-Y"}, format="json")
    assert not DeviceModel.objects.filter(code="AD-UNIT-Y").exists()


def test_support_read_only_and_customer_and_device_cannot_access_catalog():
    from .test_customer_membership import portal_user
    from .test_api import device_client
    model = catalog_model()
    client = APIClient()
    client.force_authenticate(staff_user(support=True))
    assert client.get("/api/v1/device-models/").status_code == 200
    assert client.patch(f"/api/v1/device-models/{model.pk}/", {"is_active": False}).status_code == 403
    assert client.post("/api/v1/device-models/", {}).status_code == 403
    client.force_authenticate(portal_user())
    assert client.get("/api/v1/device-models/").status_code == 403
    _, token = device_pair()
    assert device_client(token).get("/api/v1/device-models/").status_code in {401, 403}
    assert APIClient().get("/api/v1/device-models/").status_code in {401, 403}


def test_identity_cannot_change_and_inactive_model_preserves_existing_devices():
    client = admin_client()
    model = catalog_model()
    owner = customer()
    payload = {"serial_number": "CAT-1", "device_model": model.pk, "customer": owner.pk}
    created = client.post("/api/v1/devices/", payload, format="json")
    assert created.status_code == 201 and created.data["model_name"] == model.code
    for field, value in [("code", "AD-NEW"), ("kind", "pump"), ("edition", "pc")]:
        assert client.patch(f"/api/v1/device-models/{model.pk}/", {field: value}, format="json").status_code == 400
    assert client.patch(f"/api/v1/device-models/{model.pk}/", {"is_active": False, "display_name": "Renamed"}, format="json").status_code == 200
    assert client.post("/api/v1/devices/", {**payload, "serial_number": "CAT-2"}, format="json").status_code == 400
    assert client.patch(f"/api/v1/devices/{created.data['id']}/", {"device_model": model.pk, "location": "Depot"}, format="json").status_code == 200
    assert client.delete(f"/api/v1/device-models/{model.pk}/").status_code == 405


def test_multiple_models_per_customer_and_legacy_preservation():
    client = admin_client()
    owner = customer()
    for serial, model in [("MULTI-1", catalog_model()), ("MULTI-2", catalog_model("AD-PUMP-E", kind="pump", edition="e"))]:
        result = client.post("/api/v1/devices/", {"serial_number": serial, "customer": owner.pk, "device_model": model.pk}, format="json")
        assert result.status_code == 201
    assert owner.devices.count() == 2
    assert client.get("/api/v1/devices/", {"customer": owner.pk}).data["count"] == 2
    legacy, _ = device_pair(model="Old custom M1")
    assert client.patch(f"/api/v1/devices/{legacy.pk}/", {"location": "Legacy depot"}, format="json").status_code == 200
    legacy.refresh_from_db()
    assert legacy.model_name == "Old custom M1" and legacy.device_model_id is None
    assert client.patch(f"/api/v1/devices/{legacy.pk}/", {"model_name": "invented"}, format="json").status_code == 400


@pytest.mark.parametrize("data", [{}, {"device_model": None}, {"device_model": 999999}, {"model_name": "free text"}])
def test_new_device_requires_valid_catalog_selection(data):
    response = admin_client().post("/api/v1/devices/", {"serial_number": "INVALID", "customer": customer().pk, **data}, format="json")
    assert response.status_code == 400
    assert not Device.objects.filter(serial_number="INVALID").exists()


def test_case_insensitive_code_constraint():
    catalog_model()
    with pytest.raises(IntegrityError), transaction.atomic():
        DeviceModel.objects.create(code="ad-unit-b", display_name="Duplicate", kind="unit", edition="b")
