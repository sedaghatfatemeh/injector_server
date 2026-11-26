"""Customer account administration and narrowly scoped read-only portal APIs."""

from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.cache import patch_cache_control
from rest_framework import mixins, serializers, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .record_history import RecordHistorySerializerMixin
from .access import customer_membership
from .inventory import boolean_parameter
from .models import AuditEntry, Customer, CustomerMembership, Device
from .permissions import AuditedStaffActionsMixin, IsSuperAdministrator


class NoStoreMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        patch_cache_control(response, private=True, no_store=True, max_age=0)
        return response


class CustomerUserSerializer(RecordHistorySerializerMixin, serializers.ModelSerializer):
    history_target_type = "user"
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.filter(is_archived=False), write_only=True)
    organization = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ["record_history", "id", "email", "first_name", "last_name", "password", "customer", "organization", "is_active", "date_joined"]
        read_only_fields = ["id", "organization", "date_joined"]

    def get_organization(self, user):
        member = user.customer_membership
        return {"id": member.customer_id, "name": member.customer.organization_name,
                "is_archived": member.customer.is_archived}

    def validate(self, attrs):
        allowed = {"is_active"} if self.instance else {"email", "password", "first_name", "last_name", "customer"}
        unknown = set(self.initial_data) - allowed
        if unknown:
            raise ValidationError({key: "This field cannot be set." for key in sorted(unknown)})
        if self.instance:
            if not attrs:
                raise ValidationError({"is_active": "Provide the account status."})
            if attrs.get("is_active") and self.instance.customer_membership.customer.is_archived:
                raise ValidationError({"is_active": "The organization is archived."})
            return attrs
        attrs["email"] = attrs["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=attrs["email"]).exists():
            raise ValidationError({"email": "A user with this email already exists."})
        candidate = get_user_model()(email=attrs["email"], first_name=attrs.get("first_name", ""),
                                     last_name=attrs.get("last_name", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        customer = validated_data.pop("customer")
        # Share the existing staff serializer's unique username namespace. Two
        # concurrent API creations of one email (even across roles) cannot win.
        username = "staff-" + sha256(validated_data["email"].encode("utf-8")).hexdigest()
        try:
            with transaction.atomic():
                organization = Customer.objects.select_for_update().get(pk=customer.pk)
                if organization.is_archived:
                    raise ValidationError({"customer": "The organization is archived."})
                user = get_user_model().objects.create_user(username=username, is_staff=False, is_superuser=False,
                                                            **validated_data)
                membership = CustomerMembership(user=user, customer=organization)
                membership.full_clean()
                membership.save()
                return user
        except IntegrityError as exc:
            raise ValidationError({"email": "A user with this email already exists."}) from exc


class CustomerUserViewSet(NoStoreMixin, AuditedStaffActionsMixin, mixins.ListModelMixin, mixins.CreateModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    audit_target_type = "customer_user"
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsSuperAdministrator]
    serializer_class = CustomerUserSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ["email", "first_name", "last_name", "customer_membership__customer__organization_name"]

    def get_queryset(self):
        queryset = get_user_model().objects.filter(customer_membership__isnull=False).select_related(
            "customer_membership__customer",
        ).order_by("-date_joined", "-pk")
        if "is_active" in self.request.query_params:
            queryset = queryset.filter(is_active=boolean_parameter(self.request, "is_active"))
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            user = serializer.save()
            AuditEntry.objects.create(actor=self.request.user, action="customer_user.created", target_type="user",
                                      target_id=str(user.pk), details={"customer_id": user.customer_membership.customer_id})

    def perform_update(self, serializer):
        with transaction.atomic():
            # Serialize status changes with other account updates.
            serializer.instance = self.get_queryset().select_for_update(of=("self",)).get(pk=serializer.instance.pk)
            organization = Customer.objects.select_for_update().get(pk=serializer.instance.customer_membership.customer_id)
            if serializer.validated_data.get("is_active") and organization.is_archived:
                raise ValidationError({"is_active": "The organization is archived."})
            before = serializer.instance.is_active
            user = serializer.save()
            AuditEntry.objects.create(actor=self.request.user, action="customer_user.status_changed", target_type="user",
                                      target_id=str(user.pk), details={"was_active": before, "is_active": user.is_active})


class IsCustomerUser(BasePermission):
    def has_permission(self, request, view):
        request.customer_membership = customer_membership(request.user)
        return request.customer_membership is not None


class CustomerDeviceSerializer(serializers.ModelSerializer):
    is_online = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = ["id", "serial_number", "model_name", "software_version", "location", "last_seen_at", "is_online"]

    def get_is_online(self, device):
        return bool(device.last_seen_at and device.last_seen_at >= self.context["online_since"])


class CustomerScopeMixin(NoStoreMixin):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsCustomerUser]
    allowed_parameters = set()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        unknown = set(request.query_params) - self.allowed_parameters
        if unknown:
            raise ValidationError({key: "Unsupported query parameter." for key in sorted(unknown)})
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ValidationError("Query parameters cannot be repeated.")
        self.generated_at = timezone.now()
        self.online_since = self.generated_at - timedelta(minutes=settings.DEVICE_ONLINE_WINDOW_MINUTES)

    def scoped_devices(self):
        return Device.objects.filter(customer_id=self.request.customer_membership.customer_id, is_archived=False)


class CustomerDeviceViewSet(CustomerScopeMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CustomerDeviceSerializer
    allowed_parameters = {"search", "online", "page"}
    filter_backends = []
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        queryset = self.scoped_devices()
        if self.action == "list":
            search = self.request.query_params.get("search", "").strip()
            if len(search) > 200:
                raise ValidationError({"search": "Search cannot exceed 200 characters."})
            if search:
                queryset = queryset.filter(Q(serial_number__icontains=search) | Q(model_name__icontains=search))
            if "online" in self.request.query_params:
                online = boolean_parameter(self.request, "online")
                queryset = queryset.filter(last_seen_at__gte=self.online_since) if online else queryset.filter(
                    Q(last_seen_at__lt=self.online_since) | Q(last_seen_at__isnull=True),
                )
        return queryset.order_by("serial_number", "pk")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "online_since": self.online_since}


class CustomerSummary(CustomerScopeMixin, APIView):
    def get(self, request):
        queryset = self.scoped_devices()
        counts = queryset.aggregate(total=Count("pk"), online=Count("pk", filter=Q(last_seen_at__gte=self.online_since)))
        count, online = counts["total"], counts["online"]
        return Response({"device_count": count, "online_count": online, "offline_count": count - online,
                         "generated_at": self.generated_at, "online_window_minutes": settings.DEVICE_ONLINE_WINDOW_MINUTES})
