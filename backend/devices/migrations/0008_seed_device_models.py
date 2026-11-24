from django.db import migrations


def seed_models(apps, schema_editor):
    Model = apps.get_model("devices", "DeviceModel")
    Device = apps.get_model("devices", "Device")
    database = schema_editor.connection.alias
    kinds = [("unit", "UNIT", "یونیت"), ("cr", "CR", "کامان‌ریل"),
             ("combo", "COMBO", "ترکیبی یونیت و کامان‌ریل"), ("pump", "PUMP", "تست پمپ"),
             ("pro", "PRO", "تست کامل")]
    editions = [("b", "B", "باکس کنار دستگاه"), ("pc", "PC", "کامپیوتری"), ("e", "E", "اقتصادی")]
    for kind, prefix, kind_label in kinds:
        for edition, suffix, edition_label in editions:
            code = f"AD-{prefix}-{suffix}"
            model, _ = Model.objects.using(database).get_or_create(
                code=code, defaults={"kind": kind, "edition": edition,
                                     "display_name": f"{kind_label} · {edition_label}"},
            )
            # Only exact existing compatibility keys are safe to associate.
            Device.objects.using(database).filter(model_name=code, device_model__isnull=True).update(device_model=model)


class Migration(migrations.Migration):
    dependencies = [("devices", "0007_device_model_catalog")]
    operations = [migrations.RunPython(seed_models, migrations.RunPython.noop)]
