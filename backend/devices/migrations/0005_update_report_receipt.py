from django.db import migrations, models


def preserve_legacy_receipt_times(apps, schema_editor):
    assignment = apps.get_model("devices", "UpdateAssignment")
    assignment.objects.using(schema_editor.connection.alias).filter(reported_at__isnull=False).update(
        report_received_at=models.F("reported_at"),
    )


class Migration(migrations.Migration):
    dependencies = [("devices", "0004_event_receipt_time")]

    operations = [
        migrations.AddField(
            model_name="updateassignment",
            name="report_received_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(preserve_legacy_receipt_times, migrations.RunPython.noop),
    ]
