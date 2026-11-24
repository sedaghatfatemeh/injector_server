import json
import re
from urllib.parse import urlsplit
from hashlib import sha256
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from packaging.version import InvalidVersion, Version
from rest_framework import serializers

from .models import Customer, Device, DeviceEvent, DeviceModel, SoftwareRelease, UpdateAssignment
from .inventory import normalize_phone


class StaffUserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    role = serializers.ChoiceField(choices=["support", "super_admin"], default="support")

    class Meta:
        model = get_user_model()
        fields = ["id", "email", "first_name", "last_name", "password", "role", "is_active", "date_joined", "last_login"]
        read_only_fields = ["id", "is_active", "date_joined", "last_login"]

    def to_representation(self, instance):
        # The role is an API concept; Django stores flags and group membership.
        data = super().to_representation(instance)
        data["role"] = "super_admin" if instance.is_superuser else "support"
        return data

    def validate_email(self, value):
        value = value.strip().lower()
        if get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        candidate = get_user_model()(
            email=attrs["email"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        role = validated_data.pop("role", "support")
        # A deterministic internal username gives concurrent API requests for the
        # same normalized email a database-enforced uniqueness boundary.
        username = "staff-" + sha256(validated_data["email"].encode("utf-8")).hexdigest()
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    username=username, is_staff=True, is_superuser=role == "super_admin", **validated_data,
                )
                if role == "support":
                    user.groups.add(Group.objects.get_or_create(name="support")[0])
                return user
        except IntegrityError as exc:
            raise serializers.ValidationError({"email": "A user with this email already exists."}) from exc


class CustomerSerializer(serializers.ModelSerializer):
    device_count = serializers.SerializerMethodField()

    def get_device_count(self, obj):
        count = getattr(obj, "device_count", None)
        return count if count is not None else obj.devices.filter(is_archived=False).count()

    class Meta:
        model = Customer
        fields = ["id", "organization_name", "contact_name", "contact_email", "contact_phone", "address", "notes", "device_count", "is_archived", "created_at", "updated_at"]
        read_only_fields = ["id", "device_count", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        email = attrs.get("contact_email", getattr(self.instance, "contact_email", ""))
        phone = attrs.get("contact_phone", getattr(self.instance, "contact_phone", ""))
        if not email and not phone:
            raise serializers.ValidationError("Provide at least one customer contact method: email or phone.")
        return attrs

    def validate_contact_email(self, value):
        return value.strip().lower()

    def validate_contact_phone(self, value):
        return normalize_phone(value)

    def validate_organization_name(self, value):
        return value.strip()

    def validate_contact_name(self, value):
        return value.strip()


class DeviceSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(required=False, max_length=120)
    device_model = serializers.PrimaryKeyRelatedField(queryset=DeviceModel.objects.all(), required=False)
    model_display_name = serializers.CharField(source="device_model.display_name", read_only=True, default="")
    customer_name = serializers.CharField(source="customer.organization_name", read_only=True)
    customer_is_archived = serializers.BooleanField(source="customer.is_archived", read_only=True)
    is_online = serializers.SerializerMethodField()
    active_fault_count = serializers.SerializerMethodField()

    def get_is_online(self, obj):
        return bool(obj.last_seen_at and obj.last_seen_at >= timezone.now() - timedelta(minutes=settings.DEVICE_ONLINE_WINDOW_MINUTES))

    def get_active_fault_count(self, obj):
        count = getattr(obj, "active_fault_count", None)
        return count if count is not None else obj.faults.filter(state=DeviceEvent.State.ACTIVE).count()

    def get_fields(self):
        fields = super().get_fields()
        if isinstance(self.instance, Device) and self.instance.last_seen_at:
            fields["software_version"].read_only = True
        return fields

    def validate_customer(self, value):
        if value.is_archived and (self.instance is None or self.instance.customer_id != value.pk):
            raise serializers.ValidationError("Choose an active customer for a new assignment.")
        return value

    def validate_site_contact_phone(self, value):
        return normalize_phone(value)

    def validate(self, attrs):
        model = attrs.get("device_model")
        if not self.instance and model is None:
            raise serializers.ValidationError({"device_model": "Choose a catalog model."})
        if model is not None:
            if not model.is_active and (not self.instance or self.instance.device_model_id != model.pk):
                raise serializers.ValidationError({"device_model": "Choose an active model."})
            if "model_name" in attrs and attrs["model_name"] != model.code:
                raise serializers.ValidationError({"model_name": "The model name must match the selected model code."})
            attrs["model_name"] = model.code
        elif "model_name" in attrs and self.instance and attrs["model_name"] != self.instance.model_name:
            raise serializers.ValidationError({"device_model": "Choose a catalog model to change the device model."})
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        if self.instance and self.instance.is_archived and attrs.get("is_archived") is False and customer.is_archived:
            raise serializers.ValidationError({"customer": "Choose an active customer before restoring a device."})
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            model = DeviceModel.objects.select_for_update().get(pk=validated_data["device_model"].pk)
            validated_data["device_model"] = model
            self.validate(validated_data)
            return super().create(validated_data)

    def update(self, instance, validated_data):
        with transaction.atomic():
            if "device_model" in validated_data:
                validated_data["device_model"] = DeviceModel.objects.select_for_update().get(pk=validated_data["device_model"].pk)
                self.validate(validated_data)
            return super().update(instance, validated_data)

    class Meta:
        model = Device
        fields = ["id", "serial_number", "model_name", "device_model", "model_display_name", "customer", "customer_name", "customer_is_archived", "software_version", "last_seen_at", "is_online", "install_state", "active_fault_count", "location", "site_contact_name", "site_contact_phone", "is_archived", "created_at", "updated_at"]
        read_only_fields = ["id", "last_seen_at", "is_online", "install_state", "active_fault_count", "created_at", "updated_at"]


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
        url = urlsplit(value)
        if url.scheme.lower() != "https" or url.username is not None or url.password is not None or url.fragment:
            raise serializers.ValidationError("Use an HTTPS package URL without embedded credentials or a fragment.")
        return value

    def validate_sha256(self, value):
        if not re.fullmatch(r"[a-fA-F0-9]{64}", value):
            raise serializers.ValidationError("Provide the package SHA-256 digest as 64 hexadecimal characters.")
        return value.lower()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        models = attrs.get("compatible_models", [])
        if not isinstance(models, list) or any(not isinstance(model, str) or not model.strip() for model in models):
            raise serializers.ValidationError({"compatible_models": "Provide a list of non-empty model names, or an empty list for all models."})
        attrs["compatible_models"] = list(dict.fromkeys(model.strip() for model in models))
        version = attrs.get("version", getattr(self.instance, "version", ""))
        minimum_version = attrs.get("minimum_version", getattr(self.instance, "minimum_version", ""))
        try:
            Version(version.removeprefix("v"))
            if minimum_version:
                Version(minimum_version.removeprefix("v"))
        except InvalidVersion as exc:
            raise serializers.ValidationError({"version": "Version values must follow a comparable version format."}) from exc
        if self.instance and self.instance.status != SoftwareRelease.Status.DRAFT:
            for field in ("version", "package_url", "sha256", "compatible_models", "minimum_version", "release_notes", "target_all_devices", "target_devices"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError({field: "Published release metadata cannot be changed."})
        return attrs


class UpdateAssignmentSerializer(serializers.ModelSerializer):
    device_serial = serializers.CharField(source="device.serial_number", read_only=True)
    release_version = serializers.CharField(source="release.version", read_only=True)

    class Meta:
        model = UpdateAssignment
        fields = ["id", "device", "device_serial", "release", "release_version", "allow_downgrade", "state", "result_code", "reported_at", "report_received_at", "updated_at", "created_at"]
        read_only_fields = fields


class EventIngestSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    fault_id = serializers.UUIDField(required=False, allow_null=True)
    code = serializers.RegexField(r"^[A-Z0-9_]{1,100}$")
    summary = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    occurred_at = serializers.DateTimeField()
    state = serializers.ChoiceField(choices=DeviceEvent.State.choices, default=DeviceEvent.State.INFO)
    software_version = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    metadata = serializers.DictField(required=False, default=dict)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({"non_field_errors": ["Unknown event field."]})
            errors = {}
            if "state" in data and data["state"] not in DeviceEvent.State.values:
                errors["state"] = "Use info, active or resolved."
            for field in ("event_id", "fault_id", "code", "summary", "software_version"):
                if field in data and not isinstance(data[field], str):
                    if field != "fault_id" or data[field] is not None:
                        errors[field] = "Provide a string."
            if errors:
                raise serializers.ValidationError(errors)
        return super().to_internal_value(data)

    def validate_occurred_at(self, value):
        raw = self.initial_data.get("occurred_at")
        try:
            original = parse_datetime(raw) if isinstance(raw, str) else None
        except (ValueError, OverflowError):
            original = None
        if original is None or timezone.is_naive(original):
            raise serializers.ValidationError("Include an explicit timezone offset in the event timestamp.")
        received_at = self.context.get("received_at") or timezone.now()
        if value > received_at + timedelta(seconds=settings.DEVICE_EVENT_FUTURE_SKEW_SECONDS):
            raise serializers.ValidationError("Event time is beyond the allowed future clock skew.")
        return value

    def validate(self, attrs):
        if attrs["state"] in {DeviceEvent.State.ACTIVE, DeviceEvent.State.RESOLVED} and not attrs.get("fault_id"):
            raise serializers.ValidationError({"fault_id": "A stable fault_id is required for active/resolved fault updates."})
        return attrs

    def validate_metadata(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be a JSON object.")
        pending = [(value, 1)]
        while pending:
            item, depth = pending.pop()
            if isinstance(item, (dict, list)):
                if depth > settings.DEVICE_EVENT_METADATA_MAX_DEPTH:
                    raise serializers.ValidationError("Metadata nesting exceeds the allowed depth.")
                if isinstance(item, dict):
                    pending.extend((key, depth) for key in item)
                    children = item.values()
                else:
                    children = item
                pending.extend((child, depth + 1) for child in children)
            elif isinstance(item, str) and "\x00" in item:
                raise serializers.ValidationError("Metadata must not contain null characters.")
        try:
            size = len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
        except (ValueError, TypeError, UnicodeError) as exc:
            raise serializers.ValidationError("Metadata must contain valid UTF-8 JSON values.") from exc
        if size > settings.DEVICE_EVENT_METADATA_MAX_BYTES:
            raise serializers.ValidationError(f"Metadata must not exceed {settings.DEVICE_EVENT_METADATA_MAX_BYTES} bytes.")
        return value


class CheckInSerializer(serializers.Serializer):
    software_version = serializers.CharField(max_length=80, required=False, allow_blank=True)
    install_state = serializers.ChoiceField(choices=Device.InstallState.choices, required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({"non_field_errors": ["Unknown check-in field."]})
            if "install_state" in data and data["install_state"] not in Device.InstallState.values:
                raise serializers.ValidationError({"install_state": "Use idle, testing or unknown."})
            if "software_version" in data and not isinstance(data["software_version"], str):
                raise serializers.ValidationError({"software_version": "Provide a string."})
        return super().to_internal_value(data)


class UpdateResultSerializer(serializers.Serializer):
    release_version = serializers.CharField(max_length=80)
    state = serializers.ChoiceField(choices=[choice for choice in UpdateAssignment.State.choices if choice[0] != "available"])
    result_code = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    reported_at = serializers.DateTimeField(required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            if set(data) - set(self.fields):
                raise serializers.ValidationError({"non_field_errors": ["Unknown update result field."]})
            timestamp = data.get("reported_at")
            if timestamp is not None and (not isinstance(timestamp, str) or not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", timestamp)):
                raise serializers.ValidationError({"reported_at": "Provide an ISO-8601 timestamp with an explicit timezone."})
        return super().to_internal_value(data)

    def validate_reported_at(self, value):
        if value > timezone.now() + timedelta(seconds=settings.DEVICE_EVENT_FUTURE_SKEW_SECONDS):
            raise serializers.ValidationError("The report timestamp is too far in the future.")
        return value

    def validate_result_code(self, value):
        if value and not re.fullmatch(r"[A-Z0-9_]{1,120}", value):
            raise serializers.ValidationError("Use a diagnostic code containing uppercase letters, digits and underscores only.")
        return value


class RollbackSerializer(serializers.Serializer):
    device_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=1000)
    reason = serializers.CharField(max_length=1000)

    def validate_device_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("A device may only be selected once.")
        return value
