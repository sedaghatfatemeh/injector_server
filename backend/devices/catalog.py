from .record_history import RecordHistorySerializerMixin
import re

from django.db import IntegrityError, transaction
from rest_framework import mixins, serializers, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import AuditEntry, DeviceModel
from .permissions import AuditedStaffActionsMixin, IsStaffUser, IsSuperAdministrator


class DeviceModelSerializer(RecordHistorySerializerMixin, serializers.ModelSerializer):
    history_target_type = "device_model"
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    edition_label = serializers.CharField(source="get_edition_display", read_only=True)

    class Meta:
        model = DeviceModel
        fields = ["record_history", "id", "code", "display_name", "kind", "kind_label", "edition", "edition_label", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_code(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*", value):
            raise serializers.ValidationError("Use an uppercase model code such as AD-UNIT-PC.")
        query = DeviceModel.objects.filter(code__iexact=value)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise serializers.ValidationError("This model code already exists.")
        return value

    def validate(self, attrs):
        if self.instance:
            for field in ("code", "kind", "edition"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError({field: "Model identity is immutable; create a new model instead."})
        return attrs


class DeviceModelViewSet(AuditedStaffActionsMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsStaffUser]
    serializer_class = DeviceModelSerializer
    queryset = DeviceModel.objects.all()
    audit_target_type = "device_model"
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["kind", "edition", "is_active"]
    search_fields = ["code", "display_name"]

    def get_permissions(self):
        return [IsSuperAdministrator()] if self.action in {"create", "update", "partial_update"} else super().get_permissions()

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                model = serializer.save()
                AuditEntry.objects.create(actor=self.request.user, action="device_model.created",
                                          target_type="device_model", target_id=str(model.pk), details={"code": model.code})
        except IntegrityError as exc:
            if DeviceModel.objects.filter(code__iexact=serializer.validated_data["code"]).exists():
                raise ValidationError({"code": "This model code already exists."}) from exc
            raise

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.instance = DeviceModel.objects.select_for_update().get(pk=serializer.instance.pk)
            serializer.validate(serializer.validated_data)
            model = serializer.save()
            AuditEntry.objects.create(actor=self.request.user, action="device_model.updated", target_type="device_model",
                                      target_id=str(model.pk), details={"code": model.code, "is_active": model.is_active,
                                                                      "display_name": model.display_name})
