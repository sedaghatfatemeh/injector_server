from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class StaffLoginThrottleBucket(models.Model):
    """Shared, locked login counters; store a keyed digest rather than a raw IP."""

    key = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField(default=timezone.now, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)


class Customer(models.Model):
    organization_name = models.CharField(max_length=200, db_index=True)
    contact_name = models.CharField(max_length=160)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization_name"]

    def __str__(self):
        return self.organization_name


class CustomerMembership(models.Model):
    """Explicit portal identity; never infer ownership from contact details."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_membership")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="memberships")

    def clean(self):
        super().clean()
        if self.user_id and (
            self.user.is_staff or self.user.is_superuser or self.user.groups.filter(name="support").exists()
        ):
            raise ValidationError({"user": "A customer account cannot also have staff privileges."})


class Device(models.Model):
    class InstallState(models.TextChoices):
        IDLE = "idle", "Idle"
        TESTING = "testing", "Testing"
        UNKNOWN = "unknown", "Unknown"

    serial_number = models.CharField(max_length=80, unique=True, db_index=True)
    model_name = models.CharField(max_length=120, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="devices")
    software_version = models.CharField(max_length=80, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    install_state = models.CharField(max_length=16, choices=InstallState.choices, default=InstallState.UNKNOWN)
    location = models.CharField(max_length=200, blank=True)
    site_contact_name = models.CharField(max_length=160, blank=True)
    site_contact_phone = models.CharField(max_length=40, blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["serial_number"]

    @property
    def is_authenticated(self):
        # A Device is returned as request.user only after DeviceTokenAuthentication succeeds.
        return True

    @property
    def is_staff(self):
        return False

    @property
    def is_superuser(self):
        return False

    def __str__(self):
        return self.serial_number


class DeviceCredential(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name="credential")
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class DeviceEvent(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        RESOLVED = "resolved", "Resolved"
        INFO = "info", "Info"

    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="events")
    event_id = models.UUIDField()
    fault_id = models.UUIDField(null=True, blank=True, db_index=True)
    code = models.CharField(max_length=100, db_index=True)
    summary = models.CharField(max_length=300, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.INFO, db_index=True)
    software_version = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["device", "event_id"], name="uniq_device_event_id")]
        indexes = [
            models.Index(fields=["device", "-occurred_at"], name="devices_dev_device__fc2df9_idx"),
            models.Index(fields=["code", "state"], name="devices_dev_code_48d6b9_idx"),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding is False:
            raise ValueError("Device events are immutable; create a new event for each device report.")
        super().save(*args, **kwargs)


class DeviceFault(models.Model):
    """Latest device-reported state for one fault occurrence; never diagnosed server-side."""

    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="faults")
    fault_id = models.UUIDField()
    latest_event = models.ForeignKey(DeviceEvent, on_delete=models.PROTECT, related_name="current_faults")
    code = models.CharField(max_length=100)
    summary = models.CharField(max_length=300, blank=True)
    state = models.CharField(max_length=16, choices=[(DeviceEvent.State.ACTIVE, "Active"), (DeviceEvent.State.RESOLVED, "Resolved")], db_index=True)
    started_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["device", "fault_id"], name="uniq_device_fault_id")]
        ordering = ["-started_at"]


class SoftwareRelease(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        WITHDRAWN = "withdrawn", "Withdrawn"

    version = models.CharField(max_length=80, unique=True)
    package_url = models.URLField(max_length=1000)
    sha256 = models.CharField(max_length=64)
    compatible_models = models.JSONField(default=list, blank=True)
    minimum_version = models.CharField(max_length=80, blank=True)
    release_notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    target_devices = models.ManyToManyField(Device, blank=True, related_name="targeted_releases")
    target_all_devices = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_releases")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class UpdateAssignment(models.Model):
    class State(models.TextChoices):
        AVAILABLE = "available", "Available"
        DOWNLOADING = "downloading", "Downloading"
        DOWNLOADED = "downloaded", "Downloaded"
        INSTALLING = "installing", "Installing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        ROLLED_BACK = "rolled_back", "Rolled back"

    release = models.ForeignKey(SoftwareRelease, on_delete=models.PROTECT, related_name="assignments")
    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="update_assignments")
    allow_downgrade = models.BooleanField(default=False)
    state = models.CharField(max_length=16, choices=State.choices, default=State.AVAILABLE)
    result_code = models.CharField(max_length=120, blank=True)
    reported_at = models.DateTimeField(null=True, blank=True)
    report_received_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["release", "device"], name="uniq_release_device_assignment")]
        ordering = ["-updated_at"]


class AuditEntry(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100)
    outcome = models.CharField(max_length=32, default="success")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
