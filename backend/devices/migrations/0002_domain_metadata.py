from django.db import migrations, models


def create_support_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.using(schema_editor.connection.alias).get_or_create(name="support")


class Migration(migrations.Migration):
    dependencies = [("devices", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="updateassignment",
            name="reported_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(create_support_group, migrations.RunPython.noop),
    ]
