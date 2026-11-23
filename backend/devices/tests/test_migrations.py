"""Exercise real schema transitions only inside pytest's PostgreSQL test database."""

from datetime import timedelta
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_fresh_install_and_metadata_upgrade_preserve_operational_records():
    assert connection.vendor == "postgresql"
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("devices", None)])
        assert not any(name.startswith("devices_") for name in connection.introspection.table_names())
        executor = MigrationExecutor(connection)
        executor.migrate([("devices", "0001_initial")])
        old_apps = executor.loader.project_state([("devices", "0001_initial")]).apps

        User = old_apps.get_model("auth", "User")
        Customer = old_apps.get_model("devices", "Customer")
        Device = old_apps.get_model("devices", "Device")
        Event = old_apps.get_model("devices", "DeviceEvent")
        Fault = old_apps.get_model("devices", "DeviceFault")
        Credential = old_apps.get_model("devices", "DeviceCredential")
        Release = old_apps.get_model("devices", "SoftwareRelease")
        Assignment = old_apps.get_model("devices", "UpdateAssignment")
        Audit = old_apps.get_model("devices", "AuditEntry")
        user = User.objects.create(username="migration-admin", email="admin@example.test", is_staff=True, is_superuser=True)
        customer = Customer.objects.create(organization_name="Existing workshop", contact_name="Nadia", contact_phone="123")
        device = Device.objects.create(serial_number="MIGRATION-001", model_name="M1", customer=customer, software_version="1.0.0")
        occurred_at = timezone.now() - timedelta(hours=2)
        event_id, fault_id = uuid.uuid4(), uuid.uuid4()
        event = Event.objects.create(device=device, event_id=event_id, fault_id=fault_id, code="ENGINE_WARN",
                                     state="active", occurred_at=occurred_at, metadata={"source": "buffered"})
        fault = Fault.objects.create(device=device, fault_id=fault_id, latest_event=event, code="ENGINE_WARN",
                                     state="active", started_at=occurred_at)
        credential = Credential.objects.create(device=device, token_digest="a" * 64)
        release = Release.objects.create(version="1.1.0", package_url="https://packages.example.test/app.whl",
                                         sha256="b" * 64, compatible_models=["M1"], created_by=user, status="published")
        release.target_devices.add(device)
        assignment = Assignment.objects.create(device=device, release=release, state="downloaded", result_code="VERIFIED")
        audit = Audit.objects.create(actor=user, action="release.published", target_type="release", target_id=str(release.pk))

        # These guarantees must come from the migrated database, including when
        # writes bypass the API and model validation.
        with pytest.raises(IntegrityError), transaction.atomic():
            Device.objects.create(serial_number=device.serial_number, model_name="M2", customer=customer)
        with pytest.raises(IntegrityError), transaction.atomic():
            Event.objects.create(device=device, event_id=event_id, code="DUPLICATE", occurred_at=occurred_at)
        with pytest.raises(IntegrityError), transaction.atomic():
            Assignment.objects.create(device=device, release=release)

        old_apps.get_model("auth", "Group").objects.filter(name="support").delete()
        executor = MigrationExecutor(connection)
        executor.migrate([("devices", "0002_domain_metadata")])
        new_apps = executor.loader.project_state([("devices", "0002_domain_metadata")]).apps
        saved_customer = new_apps.get_model("devices", "Customer").objects.get(pk=customer.pk)
        saved_event = new_apps.get_model("devices", "DeviceEvent").objects.get(pk=event.pk)
        saved_assignment = new_apps.get_model("devices", "UpdateAssignment").objects.get(pk=assignment.pk)
        assert saved_customer.organization_name == "Existing workshop"
        assert saved_customer.address == saved_customer.notes == ""
        assert saved_customer.created_at == customer.created_at
        assert saved_event.event_id == event_id and saved_event.fault_id == fault_id
        assert saved_event.occurred_at == occurred_at and saved_event.received_at == event.received_at
        assert saved_event.metadata == {"source": "buffered"}
        assert saved_assignment.state == "downloaded" and saved_assignment.result_code == "VERIFIED"
        assert saved_assignment.reported_at is None
        assert new_apps.get_model("devices", "Device").objects.get(pk=device.pk).customer_id == customer.pk
        assert new_apps.get_model("devices", "DeviceFault").objects.get(pk=fault.pk).latest_event_id == event.pk
        assert new_apps.get_model("devices", "DeviceCredential").objects.get(pk=credential.pk).token_digest == "a" * 64
        assert new_apps.get_model("devices", "SoftwareRelease").objects.get(pk=release.pk).target_devices.filter(pk=device.pk).exists()
        assert new_apps.get_model("devices", "AuditEntry").objects.get(pk=audit.pk).actor_id == user.pk
        assert new_apps.get_model("auth", "Group").objects.filter(name="support").exists()

        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "devices_deviceevent")
        assert constraints["uniq_device_event_id"]["unique"]
        assert constraints["devices_dev_device__fc2df9_idx"]["index"]
        assert constraints["devices_dev_code_48d6b9_idx"]["index"]
        # Before 0005, reported_at represented server receipt time. Preserve it.
        legacy_receipt = timezone.now() - timedelta(hours=1)
        new_apps.get_model("devices", "UpdateAssignment").objects.filter(pk=assignment.pk).update(reported_at=legacy_receipt)
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current_apps = executor.loader.project_state(latest).apps
        current_event = current_apps.get_model("devices", "DeviceEvent").objects.get(pk=event.pk)
        assert current_event.received_at == event.received_at
        assert current_event.occurred_at == occurred_at and current_event.metadata == {"source": "buffered"}
        current_assignment = current_apps.get_model("devices", "UpdateAssignment").objects.get(pk=assignment.pk)
        assert current_assignment.reported_at == current_assignment.report_received_at == legacy_receipt
        assert current_apps.get_model("devices", "CustomerMembership").objects.count() == 0
        current_user = current_apps.get_model("auth", "User").objects.get(pk=user.pk)
        assert current_user.is_staff and current_user.is_superuser and current_user.email == user.email
    finally:
        # Restore the full current schema even when an assertion fails, so other
        # tests never inherit an intentionally downgraded schema.
        MigrationExecutor(connection).migrate(latest)
