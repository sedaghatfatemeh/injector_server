from rest_framework import serializers
from packaging.version import InvalidVersion, Version

from .models import Customer, Device, DeviceEvent, SoftwareRelease, UpdateAssignment


class CustomerSerializer(serializers.ModelSerializer):
    device_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Customer
        fields = ["id", "organization_name", "contact_name", "contact_email", "contact_phone", "device_count", "is_archived", "created_at", "updated_at"]
        read_only_fields = ["id", "device_count", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        email = attrs.get("contact_email", getattr(self.instance, "contact_email", ""))
        phone = attrs.get("contact_phone", getattr(self.instance, "contact_phone", ""))
        if not email and not phone:
            raise serializers.ValidationError("Provide at least one customer contact method: email or phone.")
        return attrs


class DeviceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.organization_name", read_only=True)
    is_online = serializers.BooleanField(read_only=True)
    active_fault_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Device
        fields = ["id", "serial_number", "model_name", "customer", "customer_name", "software_version", "last_seen_at", "is_online", "install_state", "active_fault_count", "location", "site_contact_name", "site_contact_phone", "is_archived", "created_at", "updated_at"]
        read_only_fields = ["id", "last_seen_at", "is_online", "active_fault_count", "created_at", "updated_at"]


class EventSerializer(serializers.ModelSerializer):
    device_serial = serializers.CharField(source="device.serial_number", read_only=True)
    customer_name = serializers.CharField(source="device.customer.organization_name", read_only=True)

    class Meta:
        model = DeviceEvent
        fields = ["id", "event_id", "fault_id", "device", "device_serial", "customer_name", "code", "summary", "occurred_at", "received_at", "state", "software_version", "metadata"]
        read_only_fields = fields


class ReleaseSerializer(serializers.ModelSerializer):
    target_all_devices = serializers.BooleanField(default=True)

    class Meta:
        model = SoftwareRelease
        fields = ["id", "version", "package_url", "sha256", "compatible_models", "minimum_version", "release_notes", "status", "target_all_devices", "target_devices", "created_by", "published_at", "created_at"]
        read_only_fields = ["id", "status", "created_by", "published_at", "created_at"]

    def validate_package_url(self, value):
        if not value.lower().startswith("https://"):
            raise serializers.ValidationError("Software package links must use HTTPS.")
        return value

    def validate_sha256(self, value):
        import re
        if not re.fullmatch(r"[a-fA-F0-9]{64}", value):
            raise serializers.ValidationError("Provide the package SHA-256 digest as 64 hexadecimal characters.")
        return value.lower()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        models = attrs.get("compatible_models", [])
        if not isinstance(models, list) or any(not isinstance(model, str) or not model.strip() for model in models):
            raise serializers.ValidationError({"compatible_models": "Provide a list of non-empty model names, or an empty list for all models."})
        try:
            Version(attrs["version"].removeprefix("v"))
            if attrs.get("minimum_version"):
                Version(attrs["minimum_version"].removeprefix("v"))
        except InvalidVersion as exc:
            raise serializers.ValidationError({"version": "Version values must follow a comparable version format."}) from exc
        return attrs


class UpdateAssignmentSerializer(serializers.ModelSerializer):
    device_serial = serializers.CharField(source="device.serial_number", read_only=True)
    release_version = serializers.CharField(source="release.version", read_only=True)

    class Meta:
        model = UpdateAssignment
        fields = ["id", "device", "device_serial", "release", "release_version", "allow_downgrade", "state", "result_code", "updated_at", "created_at"]
        read_only_fields = fields


class EventIngestSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    fault_id = serializers.UUIDField(required=False, allow_null=True)
    code = serializers.RegexField(r"^[A-Z0-9_]{1,100}$")
    summary = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    occurred_at = serializers.DateTimeField()
    state = serializers.ChoiceField(choices=DeviceEvent.State.choices, default=DeviceEvent.State.INFO)
    software_version = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        if attrs["occurred_at"].utcoffset() is None:
            raise serializers.ValidationError({"occurred_at": "Include a timezone offset in the event timestamp."})
        if attrs["state"] in {DeviceEvent.State.ACTIVE, DeviceEvent.State.RESOLVED} and not attrs.get("fault_id"):
            raise serializers.ValidationError({"fault_id": "A stable fault_id is required for active/resolved fault updates."})
        return attrs

    def validate_metadata(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be a JSON object.")
        return value


class CheckInSerializer(serializers.Serializer):
    software_version = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    install_state = serializers.ChoiceField(choices=Device.InstallState.choices, default=Device.InstallState.UNKNOWN)


class UpdateResultSerializer(serializers.Serializer):
    release_version = serializers.CharField(max_length=80)
    state = serializers.ChoiceField(choices=UpdateAssignment.State.choices)
    result_code = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
