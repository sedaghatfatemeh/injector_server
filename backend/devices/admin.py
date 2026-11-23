from django.contrib import admin

from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.db import transaction

from .models import AuditEntry, Customer, Device, DeviceCredential, DeviceEvent, DeviceFault, SoftwareRelease, UpdateAssignment


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("organization_name", "contact_name", "contact_email", "contact_phone", "is_archived")
    search_fields = ("organization_name", "contact_name", "contact_email", "contact_phone")
    list_filter = ("is_archived",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "model_name", "customer", "software_version", "last_seen_at", "is_archived")
    search_fields = ("serial_number", "model_name", "customer__organization_name")
    list_filter = ("model_name", "is_archived")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ("device", "code", "state", "occurred_at", "received_at")
    search_fields = ("device__serial_number", "code", "summary")
    list_filter = ("state", "code")
    readonly_fields = ("event_id", "fault_id", "device", "code", "summary", "occurred_at", "received_at", "state", "software_version", "metadata")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SoftwareRelease)
class SoftwareReleaseAdmin(admin.ModelAdmin):
    list_display = ("version", "status", "created_by", "published_at", "created_at")
    list_filter = ("status",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeviceFault)
class DeviceFaultAdmin(admin.ModelAdmin):
    list_display = ("device", "fault_id", "code", "state", "started_at", "updated_at")
    list_filter = ("state", "code")
    search_fields = ("device__serial_number", "code", "fault_id")
    readonly_fields = ("device", "fault_id", "latest_event", "code", "summary", "state", "started_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UpdateAssignment)
class UpdateAssignmentAdmin(admin.ModelAdmin):
    list_display = ("device", "release", "state", "updated_at")
    list_filter = ("state",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("action", "target_type", "target_id", "actor", "outcome", "created_at")
    list_filter = ("action", "outcome")
    readonly_fields = ("actor", "action", "target_type", "target_id", "outcome", "details", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeviceCredential)
class DeviceCredentialAdmin(admin.ModelAdmin):
    list_display = ("device", "created_at", "revoked_at")
    readonly_fields = ("device", "token_digest", "created_at", "revoked_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class StaffUserAdmin(UserAdmin):
    """Keep staff-account provisioning behind super-admin-only admin access."""

    list_display = ("username", "email", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email")
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")

    def get_queryset(self, request):
        # Customer accounts are managed only by the audited customer-user API.
        # Native staff forms must not convert a portal identity into staff.
        return super().get_queryset(request).filter(customer_membership__isnull=True)

    def has_module_permission(self, request):
        return admin.site.has_permission(request)

    def has_view_permission(self, request, obj=None):
        return admin.site.has_permission(request)

    def has_add_permission(self, request):
        return admin.site.has_permission(request)

    def has_change_permission(self, request, obj=None):
        return admin.site.has_permission(request)

    def has_delete_permission(self, request, obj=None):
        return admin.site.has_permission(request)

    def audit_user_change(self, request, obj, action):
        AuditEntry.objects.create(
            actor=request.user, action=action, target_type="user", target_id=str(obj.pk),
            details={"source": "django_admin", "actor_user_id": str(request.user.pk),
                     "is_active": obj.is_active, "is_staff": obj.is_staff, "is_superuser": obj.is_superuser},
        )

    def log_addition(self, request, obj, message):
        result = super().log_addition(request, obj, message)
        self.audit_user_change(request, obj, "staff.created")
        return result

    def log_change(self, request, obj, message):
        result = super().log_change(request, obj, message)
        self.audit_user_change(request, obj, "staff.updated")
        return result

    def log_deletions(self, request, queryset):
        for obj in queryset:
            self.audit_user_change(request, obj, "staff.deleted")
        return super().log_deletions(request, queryset)

    def response_action(self, request, queryset):
        with transaction.atomic():
            return super().response_action(request, queryset)
