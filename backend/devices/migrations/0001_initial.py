# Generated as the initial migration for existing syncdb-backed installations.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("organization_name", models.CharField(db_index=True, max_length=200)), ("contact_name", models.CharField(max_length=160)), ("contact_email", models.EmailField(blank=True, max_length=254)), ("contact_phone", models.CharField(blank=True, max_length=40)), ("is_archived", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True))],
            options={"ordering": ["organization_name"]},
        ),
        migrations.CreateModel(
            name="Device",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("serial_number", models.CharField(db_index=True, max_length=80, unique=True)), ("model_name", models.CharField(db_index=True, max_length=120)), ("software_version", models.CharField(blank=True, max_length=80)), ("last_seen_at", models.DateTimeField(blank=True, db_index=True, null=True)), ("install_state", models.CharField(choices=[("idle", "Idle"), ("testing", "Testing"), ("unknown", "Unknown")], default="unknown", max_length=16)), ("location", models.CharField(blank=True, max_length=200)), ("site_contact_name", models.CharField(blank=True, max_length=160)), ("site_contact_phone", models.CharField(blank=True, max_length=40)), ("is_archived", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="devices", to="devices.customer"))],
            options={"ordering": ["serial_number"]},
        ),
        migrations.CreateModel(
            name="DeviceCredential",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("token_digest", models.CharField(max_length=64, unique=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("revoked_at", models.DateTimeField(blank=True, null=True)), ("device", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="credential", to="devices.device"))],
        ),
        migrations.CreateModel(
            name="DeviceEvent",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("event_id", models.UUIDField()), ("fault_id", models.UUIDField(blank=True, db_index=True, null=True)), ("code", models.CharField(db_index=True, max_length=100)), ("summary", models.CharField(blank=True, max_length=300)), ("occurred_at", models.DateTimeField(db_index=True)), ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)), ("state", models.CharField(choices=[("active", "Active"), ("resolved", "Resolved"), ("info", "Info")], db_index=True, default="info", max_length=16)), ("software_version", models.CharField(blank=True, max_length=80)), ("metadata", models.JSONField(blank=True, default=dict)), ("device", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="events", to="devices.device"))],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
        migrations.CreateModel(
            name="DeviceFault",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("fault_id", models.UUIDField()), ("code", models.CharField(max_length=100)), ("summary", models.CharField(blank=True, max_length=300)), ("state", models.CharField(choices=[("active", "Active"), ("resolved", "Resolved")], db_index=True, max_length=16)), ("started_at", models.DateTimeField()), ("updated_at", models.DateTimeField(auto_now=True)), ("device", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="faults", to="devices.device")), ("latest_event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="current_faults", to="devices.deviceevent"))],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="SoftwareRelease",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("version", models.CharField(max_length=80, unique=True)), ("package_url", models.URLField(max_length=1000)), ("sha256", models.CharField(max_length=64)), ("compatible_models", models.JSONField(blank=True, default=list)), ("minimum_version", models.CharField(blank=True, max_length=80)), ("release_notes", models.TextField(blank=True)), ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("withdrawn", "Withdrawn")], default="draft", max_length=16)), ("target_all_devices", models.BooleanField(default=False)), ("published_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_releases", to=settings.AUTH_USER_MODEL)), ("target_devices", models.ManyToManyField(blank=True, related_name="targeted_releases", to="devices.device"))],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="UpdateAssignment",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("allow_downgrade", models.BooleanField(default=False)), ("state", models.CharField(choices=[("available", "Available"), ("downloading", "Downloading"), ("downloaded", "Downloaded"), ("installing", "Installing"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("rolled_back", "Rolled back")], default="available", max_length=16)), ("result_code", models.CharField(blank=True, max_length=120)), ("updated_at", models.DateTimeField(auto_now=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("device", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="update_assignments", to="devices.device")), ("release", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assignments", to="devices.softwarerelease"))],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="AuditEntry",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("action", models.CharField(db_index=True, max_length=100)), ("target_type", models.CharField(max_length=100)), ("target_id", models.CharField(max_length=100)), ("outcome", models.CharField(default="success", max_length=32)), ("details", models.JSONField(blank=True, default=dict)), ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)), ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL))],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(model_name="deviceevent", constraint=models.UniqueConstraint(fields=("device", "event_id"), name="uniq_device_event_id")),
        migrations.AddIndex(model_name="deviceevent", index=models.Index(fields=["device", "-occurred_at"], name="devices_dev_device__fc2df9_idx")),
        migrations.AddIndex(model_name="deviceevent", index=models.Index(fields=["code", "state"], name="devices_dev_code_48d6b9_idx")),
        migrations.AddConstraint(model_name="devicefault", constraint=models.UniqueConstraint(fields=("device", "fault_id"), name="uniq_device_fault_id")),
        migrations.AddConstraint(model_name="updateassignment", constraint=models.UniqueConstraint(fields=("release", "device"), name="uniq_release_device_assignment")),
    ]
