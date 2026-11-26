from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from devices.inventory import device_inventory
from devices.models import AuditEntry, Customer, Device
from devices.serializers import DeviceSerializer
from .test_api import staff_user, device_pair
from .test_customer_membership import portal_user

pytestmark = pytest.mark.django_db


def operator(name="Operator"):
    user = staff_user(superuser=True)
    user.first_name = name
    user.save()
    client = APIClient()
    client.force_authenticate(user)
    return user, client


def test_creation_edit_and_archive_metadata_is_server_owned_and_atomic():
    user, client = operator("Original operator")
    payload = {"organization_name": "Workshop", "contact_name": "Owner", "contact_phone": "123",
               "record_history": {"created": {"at": "1900-01-01", "by": "forged"}}}
    created = client.post("/api/v1/customers/", payload, format="json")
    assert created.status_code == 201
    identity = created.data["id"]
    assert created.data["record_history"]["created"]["by"] == "Original operator"
    assert created.data["record_history"]["edited"] is None
    url = f"/api/v1/customers/{identity}/"
    with patch("devices.views.AuditEntry.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            client.patch(url, {"contact_name": "Lost edit"}, format="json")
    assert Customer.objects.get(pk=identity).contact_name == "Owner"
    edited = client.patch(url, {"contact_name": "New owner"}, format="json")
    assert edited.data["record_history"]["edited"]["by"] == "Original operator"
    assert client.delete(url).status_code == 204
    history = client.get(url, {"is_archived": "true"}).data["record_history"]
    entry = AuditEntry.objects.get(action="customer.archived", target_id=str(identity))
    assert history["archived"]["at"] == entry.created_at.isoformat().replace("+00:00", "Z")
    assert history["archived"]["by"] == "Original operator"
    assert history["edited"] == history["archived"]
    assert not any(key in str(history) for key in ["password", "token", "contact_phone", "details"])


def test_new_actor_snapshot_survives_actor_rename_and_deletion():
    actor, client = operator("Original name")
    created = client.post("/api/v1/customers/", {"organization_name": "History", "contact_name": "Owner", "contact_phone": "123"}, format="json")
    identity = created.data["id"]
    actor.first_name = "Changed name"
    actor.save()
    assert AuditEntry.objects.get(action="customer.created", target_id=str(identity)).actor_label == "Original name"
    actor.delete()
    _, reader = operator("Reader")
    response = reader.get(f"/api/v1/customers/{identity}/")
    assert response.data["record_history"]["created"]["by"] == "Original name"


def test_legacy_unknowns_and_communication_do_not_invent_an_editor():
    device, _ = device_pair(model="Legacy model")
    device.is_archived = True
    device.save()
    _, client = operator()
    result = client.get(f"/api/v1/devices/{device.pk}/", {"is_archived": "true"})
    history = result.data["record_history"]
    assert history["created"]["at"]
    assert history["created"]["by"] is None
    assert history["edited"] is None and history["archived"] is None


def test_history_is_batched_and_not_one_query_per_device():
    user, _ = operator()
    owner = Customer.objects.create(organization_name="Fleet", contact_name="Owner")
    Device.objects.bulk_create([Device(serial_number=f"HISTORY-{i}", model_name="M", customer=owner) for i in range(50)])
    devices = list(device_inventory())
    AuditEntry.objects.bulk_create([AuditEntry(actor=user, actor_label="Snapshot", action="device.registered", target_type="device", target_id=str(device.pk)) for device in devices])
    with CaptureQueriesContext(connection) as captured:
        data = DeviceSerializer(devices, many=True, context={"request": SimpleNamespace(user=user)}).data
    assert len(data) == 50
    assert sum('FROM "devices_auditentry"' in query["sql"] for query in captured) == 1
    assert len(captured) <= 3
    assert all(row["record_history"]["created"]["by"] == "Snapshot" for row in data)


def test_customer_cannot_receive_staff_history_even_with_extra_parameters():
    device, _ = device_pair()
    user = portal_user(customer=device.customer)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/customer/devices/", {"search": device.serial_number})
    assert response.status_code == 200
    assert "record_history" not in response.data["results"][0]
    assert client.get(f"/api/v1/devices/{device.pk}/").status_code == 403
    serialized = DeviceSerializer(device, context={"request": SimpleNamespace(user=user)}).data
    assert serialized["record_history"] is None


def test_catalog_accounts_and_release_history_use_their_existing_audited_operations():
    user, client = operator("Lifecycle operator")
    model = client.post("/api/v1/device-models/", {"code": "AD-EXTRA-E", "display_name": "Extra", "kind": "unit", "edition": "e"}, format="json")
    assert model.status_code == 201 and model.data["record_history"]["created"]["by"] == "Lifecycle operator"
    staff = client.post("/api/v1/staff-users/", {"email": "new-staff@example.test", "password": "Correct-Horse-42!", "role": "support"}, format="json")
    assert staff.status_code == 201 and staff.data["record_history"]["created"]["by"] == "Lifecycle operator"
    owner = Customer.objects.create(organization_name="Owner", contact_name="Operator")
    account = client.post("/api/v1/customer-users/", {"email": "new-customer@example.test", "password": "Correct-Horse-42!", "customer": owner.pk}, format="json")
    assert account.status_code == 201 and account.data["record_history"]["created"]["by"] == "Lifecycle operator"
    changed = client.patch(f"/api/v1/customer-users/{account.data['id']}/", {"is_active": False}, format="json")
    assert changed.data["record_history"]["edited"]["by"] == "Lifecycle operator"
    release = client.post("/api/v1/releases/", {"version": "9.0.0", "package_url": "https://example.test/package.whl", "sha256": "a" * 64, "target_all_devices": True}, format="json")
    assert release.status_code == 201 and release.data["record_history"]["created"]["by"] == "Lifecycle operator"
    assert client.post(f"/api/v1/releases/{release.data['id']}/withdraw/").status_code == 200
    assert client.get(f"/api/v1/releases/{release.data['id']}/").data["record_history"]["withdrawn"]["by"] == "Lifecycle operator"


@pytest.mark.django_db(transaction=True)
def test_snapshot_migration_preserves_old_audit_content_without_fabricating_a_name():
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("devices", "0008_seed_device_models")])
        apps = executor.loader.project_state([("devices", "0008_seed_device_models")]).apps
        audit = apps.get_model("devices", "AuditEntry").objects.create(action="customer.archived", target_type="customer", target_id="999", details={"preserved": True})
        at = audit.created_at
        MigrationExecutor(connection).migrate(latest)
        migrated = AuditEntry.objects.get(pk=audit.pk)
        assert migrated.actor_label == ""
        assert migrated.actor_id is None and migrated.created_at == at
        assert migrated.details == {"preserved": True}
        # A previous app version can still write during a rolling deployment.
        old_write = apps.get_model("devices", "AuditEntry").objects.create(action="customer.created", target_type="customer", target_id="1000")
        assert AuditEntry.objects.get(pk=old_write.pk).actor_label == ""
    finally:
        MigrationExecutor(connection).migrate(latest)
