from django.contrib import admin

from .models import AuditEntry, Customer, Device, DeviceEvent, DeviceFault, SoftwareRelease, UpdateAssignment


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
    readonly_fields = ("event_id", "device", "code", "summary", "occurred_at", "received_at", "state", "software_version", "metadata")


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
