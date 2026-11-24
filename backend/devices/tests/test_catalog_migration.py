import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_catalog_upgrade_preserves_legacy_release_keys_and_multiple_customer_devices():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("devices", "0006_customer_membership")])
        apps = executor.loader.project_state([("devices", "0006_customer_membership")]).apps
        owner = apps.get_model("devices", "Customer").objects.create(
            organization_name="Migration owner", contact_name="Operator", contact_phone="123",
        )
        Device = apps.get_model("devices", "Device")
        known = Device.objects.create(serial_number="EXACT-CODE", model_name="AD-UNIT-PC", customer=owner)
        legacy = Device.objects.create(serial_number="LEGACY-CODE", model_name="Custom model M1", customer=owner)
        user = apps.get_model("auth", "User").objects.create(username="catalog-migration-admin")
        release = apps.get_model("devices", "SoftwareRelease").objects.create(
            version="migration-1", package_url="https://example.test/package.whl", sha256="a" * 64,
            compatible_models=["AD-UNIT-PC", "Custom model M1"], created_by=user,
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        Model = apps.get_model("devices", "DeviceModel")
        Device = apps.get_model("devices", "Device")
        assert Model.objects.count() == 15
        assert set(Model.objects.values_list("code", flat=True)) == {
            f"AD-{kind}-{edition}" for kind in ["UNIT", "CR", "COMBO", "PUMP", "PRO"] for edition in ["B", "PC", "E"]
        }
        assert Device.objects.get(pk=known.pk).device_model.code == "AD-UNIT-PC"
        assert Device.objects.get(pk=legacy.pk).device_model_id is None
        assert Device.objects.get(pk=legacy.pk).model_name == "Custom model M1"
        assert Device.objects.filter(customer_id=owner.pk).count() == 2
        assert apps.get_model("devices", "SoftwareRelease").objects.get(pk=release.pk).compatible_models == ["AD-UNIT-PC", "Custom model M1"]
    finally:
        MigrationExecutor(connection).migrate(latest)
