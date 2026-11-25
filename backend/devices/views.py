from datetime import timedelta
from django.conf import settings

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from packaging.version import InvalidVersion, Version
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action, api_view, authentication_classes, parser_classes, permission_classes, throttle_classes
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .authentication import DeviceTokenAuthentication, issue_device_token, lock_authenticated_device, revoke_device_token
from .parsers import CheckInJSONParser, EventBatchJSONParser
from .ingestion import ingest_event, safe_event_id
from .inventory import CUSTOMER_AUDIT_FIELDS, DEVICE_AUDIT_FIELDS, CustomerSearchFilter, InventoryOrderingFilter, boolean_parameter, device_inventory, snapshot
from .throttling import DeviceCheckInThrottle, DeviceEventsThrottle, DeviceManifestThrottle, DeviceUpdateResultThrottle, LoginThrottle
from .models import AuditEntry, Customer, Device, DeviceEvent, DeviceFault, SoftwareRelease, UpdateAssignment
from .permissions import AuditedStaffActionsMixin, IsBrowserUser, IsStaffUser, IsSuperAdministrator
from .access import browser_identity
from .serializers import CheckInSerializer, CustomerSerializer, DeviceSerializer, EventIngestSerializer, EventSerializer, ReleaseSerializer, UpdateAssignmentSerializer, UpdateResultSerializer
from .serializers import RollbackSerializer, StaffUserSerializer
from .releases import record_update_result
from .inventory import archive_inventory


class StaffUserViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsSuperAdministrator]
    serializer_class = StaffUserSerializer
    search_fields = ["email", "first_name", "last_name"]

    def get_queryset(self):
        queryset = get_user_model().objects.filter(
            Q(is_superuser=True) | Q(is_staff=True, groups__name="support")
        ).distinct().order_by("-date_joined", "-pk")
        if "is_active" in self.request.query_params:
            queryset = queryset.filter(is_active=boolean_parameter(self.request, "is_active"))
        return queryset

    def permission_denied(self, request, message=None, code=None):
        actor = request.user if isinstance(request.user, get_user_model()) else None
        AuditEntry.objects.create(
            actor=actor,
            action="staff.provision_denied" if request.method == "POST" else "staff.access_denied",
            target_type="user", target_id="", outcome="denied",
        )
        return super().permission_denied(request, message=message, code=code)

    def perform_create(self, serializer):
        with transaction.atomic():
            user = serializer.save()
            AuditEntry.objects.create(
                actor=self.request.user, action="staff.created", target_type="user", target_id=str(user.pk),
                details={"role": "super_admin" if user.is_superuser else "support"},
            )


@never_cache
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def csrf_token(request):
    return Response({"csrfToken": get_token(request)})


class CustomerViewSet(AuditedStaffActionsMixin, viewsets.ModelViewSet):
    audit_target_type = "customer"
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]
    search_fields = ["organization_name", "contact_name", "contact_email", "contact_phone"]
    filterset_fields = ["is_archived"]
    filter_backends = [DjangoFilterBackend, CustomerSearchFilter, InventoryOrderingFilter]
    ordering_fields = ["organization_name", "created_at"]

    def get_queryset(self):
        queryset = archive_inventory(Customer.objects.all(), self.request)
        return queryset.annotate(device_count=Count("devices", filter=Q(devices__is_archived=False))).order_by("organization_name", "pk")

    def perform_create(self, serializer):
        with transaction.atomic():
            customer = serializer.save()
            AuditEntry.objects.create(actor=self.request.user, action="customer.created", target_type="customer", target_id=str(customer.pk))

    def perform_update(self, serializer):
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=serializer.instance.pk)
            serializer.instance = customer
            serializer.validate(dict(serializer.validated_data))
            before = snapshot(customer, CUSTOMER_AUDIT_FIELDS)
            customer = serializer.save()
            AuditEntry.objects.create(actor=self.request.user, action="customer.updated", target_type="customer",
                                      target_id=str(customer.pk), details={"before": before, "after": snapshot(customer, CUSTOMER_AUDIT_FIELDS)})

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSuperAdministrator()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance = Customer.objects.select_for_update().get(pk=instance.pk)
            instance.is_archived = True
            instance.save(update_fields=["is_archived", "updated_at"])
            AuditEntry.objects.create(actor=self.request.user, action="customer.archived", target_type="customer", target_id=str(instance.pk))

    @action(detail=True, methods=["get"])
    def devices(self, request, pk=None):
        customer = self.get_object()
        queryset = device_inventory().filter(customer=customer)
        if not boolean_parameter(request, "include_archived_devices"):
            queryset = queryset.filter(is_archived=False)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(DeviceSerializer(page, many=True, context=self.get_serializer_context()).data)


class DeviceViewSet(AuditedStaffActionsMixin, viewsets.ModelViewSet):
    audit_target_type = "device"
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]
    search_fields = ["serial_number", "model_name", "customer__organization_name"]
    filterset_fields = ["customer", "model_name", "device_model", "is_archived"]
    filter_backends = [DjangoFilterBackend, SearchFilter, InventoryOrderingFilter]
    ordering_fields = ["serial_number", "model_name", "last_seen_at", "created_at"]

    def get_queryset(self):
        return archive_inventory(device_inventory(), self.request)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        online = self.request.query_params.get("online")
        online_since = timezone.now() - timedelta(minutes=settings.DEVICE_ONLINE_WINDOW_MINUTES)
        if online == "true":
            queryset = queryset.filter(last_seen_at__gte=online_since)
        elif online == "false":
            queryset = queryset.filter(Q(last_seen_at__lt=online_since) | Q(last_seen_at__isnull=True))
        elif online is not None:
            raise ValidationError({"online": "Use true or false."})
        has_faults = self.request.query_params.get("has_active_faults")
        if has_faults == "true":
            queryset = queryset.filter(faults__state=DeviceEvent.State.ACTIVE).distinct()
        elif has_faults == "false":
            queryset = queryset.exclude(faults__state=DeviceEvent.State.ACTIVE)
        elif has_faults is not None:
            raise ValidationError({"has_active_faults": "Use true or false."})
        return queryset

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSuperAdministrator()]
        return super().get_permissions()

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                customer = Customer.objects.select_for_update().get(pk=serializer.validated_data["customer"].pk)
                serializer.validate_customer(customer)
                device = serializer.save(customer=customer)
                AuditEntry.objects.create(actor=self.request.user, action="device.registered", target_type="device", target_id=str(device.pk),
                                          details={"serial_number": device.serial_number, "customer_id": device.customer_id})
        except IntegrityError as exc:
            self.raise_serial_conflict(serializer, exc)

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                device = Device.objects.select_for_update().get(pk=serializer.instance.pk)
                serializer.instance = device
                target = serializer.validated_data.get("customer")
                target_id = target.pk if target is not None else device.customer_id
                customer = Customer.objects.select_for_update().get(pk=target_id)
                serializer.validate_customer(customer)
                serializer.validate({**serializer.validated_data, "customer": customer})
                before = snapshot(device, DEVICE_AUDIT_FIELDS)
                overrides = {"customer": customer}
                if device.last_seen_at:
                    overrides["software_version"] = device.software_version
                device = serializer.save(**overrides)
                AuditEntry.objects.create(actor=self.request.user, action="device.updated", target_type="device", target_id=str(device.pk),
                                          details={"serial_number": device.serial_number, "customer_changed": before["customer_id"] != device.customer_id,
                                                   "before": before, "after": snapshot(device, DEVICE_AUDIT_FIELDS)})
        except IntegrityError as exc:
            self.raise_serial_conflict(serializer, exc)

    def raise_serial_conflict(self, serializer, error):
        instance = serializer.instance
        serial = serializer.validated_data.get("serial_number", getattr(instance, "serial_number", ""))
        conflicts = Device.objects.filter(serial_number=serial)
        if instance:
            conflicts = conflicts.exclude(pk=instance.pk)
        if conflicts.exists():
            raise ValidationError({"serial_number": "A device with this serial number already exists."}) from error
        raise error

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance = Device.objects.select_for_update().get(pk=instance.pk)
            instance.is_archived = True
            instance.save(update_fields=["is_archived", "updated_at"])
            AuditEntry.objects.create(actor=self.request.user, action="device.archived", target_type="device", target_id=str(instance.pk))

    @action(detail=True, methods=["post"], permission_classes=[IsSuperAdministrator])
    def provision_credential(self, request, pk=None):
        device = self.get_object()
        try:
            token = issue_device_token(device, actor=request.user, source="staff_api")
        except ValueError as exc:
            raise ValidationError({"device": str(exc)}) from exc
        return Response({"credential": token, "shown_once": True}, status=status.HTTP_201_CREATED,
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    @action(detail=True, methods=["post"], permission_classes=[IsSuperAdministrator])
    def revoke_credential(self, request, pk=None):
        changed = revoke_device_token(self.get_object(), actor=request.user, source="staff_api")
        return Response({"revoked": True, "changed": changed})

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        device = self.get_object()
        queryset = device.events.select_related("device", "device__customer")
        if device.customer.is_archived and not boolean_parameter(request, "device__customer__is_archived"):
            queryset = queryset.none()
        page = self.paginate_queryset(queryset)
        serializer = EventSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def updates(self, request, pk=None):
        device = self.get_object()
        if device.customer.is_archived and not boolean_parameter(request, "device__customer__is_archived"):
            return Response({"count": 0, "next": None, "previous": None, "results": []})
        page = self.paginate_queryset(device.update_assignments.select_related("release", "device"))
        return self.get_paginated_response(UpdateAssignmentSerializer(page, many=True).data)


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]
    filterset_fields = {
        "device": ["exact"], "device__customer": ["exact"], "code": ["exact"], "state": ["exact"],
        "device__serial_number": ["icontains"],
        "device__customer__organization_name": ["icontains"],
    }
    search_fields = ["device__serial_number", "device__customer__organization_name", "code", "summary"]
    ordering_fields = ["occurred_at", "received_at", "code"]

    def get_queryset(self):
        queryset = DeviceEvent.objects.select_related("device", "device__customer")
        start = self.request.query_params.get("occurred_after")
        end = self.request.query_params.get("occurred_before")
        start_value = None
        if start:
            try:
                value = parse_datetime(start)
            except ValueError:
                value = None
            if value is None or timezone.is_naive(value):
                raise ValidationError({"occurred_after": "Provide an ISO-8601 date-time including timezone."})
            start_value = value
            queryset = queryset.filter(occurred_at__gte=value)
        if end:
            try:
                value = parse_datetime(end)
            except ValueError:
                value = None
            if value is None or timezone.is_naive(value):
                raise ValidationError({"occurred_before": "Provide an ISO-8601 date-time including timezone."})
            if start_value is not None and start_value > value:
                raise ValidationError({"occurred_before": "End time must not precede start time."})
            queryset = queryset.filter(occurred_at__lte=value)
        if self.request.query_params.get("device__is_archived") != "true":
            queryset = queryset.filter(device__is_archived=False)
        if self.request.query_params.get("device__customer__is_archived") != "true":
            queryset = queryset.filter(device__customer__is_archived=False)
        return queryset


class ReleaseViewSet(AuditedStaffActionsMixin, viewsets.ModelViewSet):
    audit_target_type = "release"
    serializer_class = ReleaseSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_queryset(self):
        return SoftwareRelease.objects.all().order_by("-created_at", "-pk")

    def get_permissions(self):
        if self.action in {"create", "withdraw", "rollback"}:
            return [IsSuperAdministrator()]
        return super().get_permissions()

    def perform_create(self, serializer):
        targets = serializer.validated_data.get("target_devices", [])
        target_all = serializer.validated_data.get("target_all_devices", False)
        if target_all == bool(targets):
            raise ValidationError("Choose either all compatible devices or a non-empty list of selected devices.")
        if any(device.is_archived or device.customer.is_archived for device in targets):
            raise ValidationError({"target_devices": "Archived devices cannot receive releases."})
        with transaction.atomic():
            release = serializer.save(
                created_by=self.request.user,
                status=SoftwareRelease.Status.PUBLISHED,
                published_at=timezone.now(),
                target_all_devices=target_all,
            )
            devices = Device.objects.filter(is_archived=False, customer__is_archived=False) if target_all else release.target_devices.filter(is_archived=False, customer__is_archived=False)
            if release.compatible_models:
                compatible = devices.filter(model_name__in=release.compatible_models)
                if not target_all and compatible.count() != devices.count():
                    raise ValidationError({"target_devices": "Every selected device must match a compatible model."})
                devices = compatible
            compatible_device_ids = [device.pk for device in devices if release_is_eligible(device, release)]
            UpdateAssignment.objects.bulk_create(
                [UpdateAssignment(release=release, device_id=device_id) for device_id in compatible_device_ids],
                ignore_conflicts=True,
            )
            AuditEntry.objects.create(
                actor=self.request.user,
                action="release.published_automatically",
                target_type="release",
                target_id=str(release.pk),
                details={"version": release.version, "device_count": len(compatible_device_ids)},
            )

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        with transaction.atomic():
            release = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
            if release.status != SoftwareRelease.Status.PUBLISHED:
                raise ValidationError({"status": "Only a published release can be withdrawn."})
            release.status = SoftwareRelease.Status.WITHDRAWN
            release.save(update_fields=["status"])
            AuditEntry.objects.create(actor=request.user, action="release.withdrawn", target_type="release", target_id=str(release.pk))
        return Response(self.get_serializer(release).data)

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        serializer = RollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device_ids = serializer.validated_data["device_ids"]
        reason = serializer.validated_data["reason"]
        with transaction.atomic():
            release = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
            if release.status != SoftwareRelease.Status.PUBLISHED:
                raise ValidationError({"release": "Only a published, retained release can be assigned for rollback."})
            devices = list(Device.objects.select_for_update(of=("self",)).filter(
                pk__in=device_ids, is_archived=False, customer__is_archived=False,
            ).order_by("pk"))
            if len(devices) != len(device_ids):
                raise ValidationError({"device_ids": "One or more devices do not exist or are archived."})
            for device in devices:
                if release.compatible_models and device.model_name not in release.compatible_models:
                    raise ValidationError({"device_ids": "Every selected device must match a compatible model."})
                if not release_is_eligible(device, release, allow_downgrade=True):
                    raise ValidationError({"device_ids": "Every selected device must report a compatible newer version."})
            for device in devices:
                UpdateAssignment.objects.update_or_create(
                    release=release, device=device,
                    defaults={"allow_downgrade": True, "state": UpdateAssignment.State.AVAILABLE,
                              "result_code": "", "reported_at": None, "report_received_at": None},
                )
            AuditEntry.objects.create(
                actor=request.user, action="release.rollback_assigned", target_type="release", target_id=str(release.pk),
                details={"version": release.version, "device_serials": [d.serial_number for d in devices], "reason": reason},
            )
        return Response({"release_version": release.version, "assigned_devices": [d.serial_number for d in devices]})

    @action(detail=False, methods=["get"], url_path="assignments")
    def assignments(self, request):
        qs = UpdateAssignment.objects.select_related("device", "release").order_by("-updated_at", "-pk")
        device = request.query_params.get("device")
        if device:
            qs = qs.filter(device__serial_number=device)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(UpdateAssignmentSerializer(page, many=True).data)


def release_is_eligible(device, release, allow_downgrade=False):
    if not device.software_version:
        return not allow_downgrade and not release.minimum_version
    try:
        current = Version(device.software_version.removeprefix("v"))
        target = Version(release.version.removeprefix("v"))
        minimum = Version(release.minimum_version.removeprefix("v")) if release.minimum_version else None
    except InvalidVersion:
        return False
    version_match = target < current if allow_downgrade else target > current
    return version_match and (minimum is None or current >= minimum)


def available_release_for(device):
    if device.is_archived or device.customer.is_archived:
        return None
    rollback_assignments = UpdateAssignment.objects.select_related("release").filter(
        device=device,
        allow_downgrade=True,
        state=UpdateAssignment.State.AVAILABLE,
        release__status=SoftwareRelease.Status.PUBLISHED,
    ).order_by("-updated_at")
    for assignment in rollback_assignments:
        if (not assignment.release.compatible_models or device.model_name in assignment.release.compatible_models) and release_is_eligible(device, assignment.release, allow_downgrade=True):
            return assignment.release

    releases = SoftwareRelease.objects.filter(status=SoftwareRelease.Status.PUBLISHED).filter(
        Q(target_all_devices=True) | Q(target_devices=device) | Q(assignments__device=device)
    )
    releases = releases.filter(Q(compatible_models=[]) | Q(compatible_models__contains=[device.model_name]))
    for release in releases.distinct().order_by("-published_at", "-pk"):
        assignment = UpdateAssignment.objects.filter(release=release, device=device).first()
        if assignment is None or (assignment.state == UpdateAssignment.State.AVAILABLE and not assignment.allow_downgrade):
            if release_is_eligible(device, release):
                return release
    return None


@never_cache
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def staff_login(request):
    SessionAuthentication().enforce_csrf(request)
    email = request.data.get("email", "")
    password = request.data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        AuditEntry.objects.create(action="staff.sign_in_failed", target_type="user", target_id="", outcome="denied")
        raise AuthenticationFailed("Email or password is incorrect.")
    email = email.strip().lower()
    User = get_user_model()
    matching_users = User.objects.filter(email__iexact=email, is_active=True).order_by("pk")
    user_record = matching_users.first() if matching_users.count() == 1 else None
    user = authenticate(request, username=user_record.get_username(), password=password) if user_record else None
    if user_record is None:
        # Match Django's unknown-user hashing work; do not make absent emails
        # a shortcut around password hashing.
        User().set_password(password)
    identity = browser_identity(user)
    if identity is None:
        AuditEntry.objects.create(action="staff.sign_in_failed", target_type="user",
                                  target_id=str(user_record.pk) if user_record else "", outcome="denied")
        raise AuthenticationFailed("Email or password is incorrect.")
    from django.contrib.auth import login
    backend = getattr(user, "backend", None) or "django.contrib.auth.backends.ModelBackend"
    with transaction.atomic():
        AuditEntry.objects.create(actor=user, action=f"{identity['role'] if identity['role'] == 'customer' else 'staff'}.signed_in",
                                  target_type="user", target_id=str(user.pk))
        login(request, user, backend=backend)
        request.session.cycle_key()
        request.session.set_expiry(settings.STAFF_SESSION_AGE_SECONDS)
    return Response({"authenticated": True, **identity})


@never_cache
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def staff_logout(request):
    from django.contrib.auth import logout
    from .models import CustomerMembership
    source = "customer" if CustomerMembership.objects.filter(user=request.user).exists() else "staff"
    AuditEntry.objects.create(actor=request.user, action=f"{source}.signed_out", target_type="user", target_id=str(request.user.pk))
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@never_cache
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsBrowserUser])
def staff_session(request):
    return Response(request.browser_identity)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStaffUser])
def dashboard_summary(request):
    online_since = timezone.now() - timedelta(minutes=settings.DEVICE_ONLINE_WINDOW_MINUTES)
    devices = Device.objects.filter(is_archived=False)
    return Response({
        "device_count": devices.count(),
        "online_count": devices.filter(last_seen_at__gte=online_since).count(),
        "offline_count": devices.filter(Q(last_seen_at__lt=online_since) | Q(last_seen_at__isnull=True)).count(),
        "active_fault_count": DeviceFault.objects.filter(device__is_archived=False, state=DeviceEvent.State.ACTIVE).count(),
        "event_count_24h": DeviceEvent.objects.filter(received_at__gte=timezone.now() - timedelta(hours=24)).count(),
        "generated_at": timezone.now(),
        "online_window_minutes": settings.DEVICE_ONLINE_WINDOW_MINUTES,
    })


@api_view(["POST"])
@authentication_classes([DeviceTokenAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([CheckInJSONParser])
@throttle_classes([DeviceCheckInThrottle])
def device_check_in(request):
    received_at = timezone.now()
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    serializer = CheckInSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        device = lock_authenticated_device(device, request.auth)
        if device.last_seen_at and received_at < device.last_seen_at:
            return Response({"accepted": True, "server_time": device.last_seen_at, "update_available": False})
        device.software_version = serializer.validated_data.get("software_version", device.software_version)
        device.install_state = serializer.validated_data.get("install_state", device.install_state)
        device.last_seen_at = received_at
        device.save(update_fields=["software_version", "install_state", "last_seen_at", "updated_at"])
    rollout_allowed = settings.DEBUG or settings.DEVICE_UPDATE_ROLLOUT_ENABLED
    update_available = rollout_allowed and device.install_state == Device.InstallState.IDLE and available_release_for(device) is not None
    return Response({"accepted": True, "server_time": device.last_seen_at, "update_available": update_available})


@api_view(["POST"])
@authentication_classes([DeviceTokenAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([DeviceEventsThrottle])
@parser_classes([EventBatchJSONParser])
def ingest_events(request):
    event_receipt_time = timezone.now()
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    payload = request.data
    if not isinstance(payload, dict):
        raise ValidationError({"events": "Provide a JSON object containing an events array."})
    unknown = set(payload) - {"events"}
    if unknown:
        raise ValidationError({"events": "Unknown event batch field. Only events is allowed."})
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events or len(raw_events) > settings.DEVICE_EVENT_BATCH_MAX:
        raise ValidationError({"events": f"Provide between 1 and {settings.DEVICE_EVENT_BATCH_MAX} events per batch."})
    results = []
    for raw_event in raw_events:
        reference = safe_event_id(raw_event)
        if not isinstance(raw_event, dict):
            errors = {"event": ["Each event must be a JSON object."]}
        else:
            serializer = EventIngestSerializer(data=raw_event, context={"received_at": event_receipt_time})
            if serializer.is_valid():
                results.append(ingest_event(device, request.auth, serializer.validated_data, event_receipt_time))
                continue
            errors = serializer.errors
        results.append({"event_id": reference, "status": "rejected", "errors": errors})
        AuditEntry.objects.create(
            action="device.event_rejected", target_type="device", target_id=str(device.pk), outcome="rejected",
            details={"event_id": reference, "reason": "invalid_payload"},
        )
    return Response({"results": results}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([DeviceTokenAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([DeviceManifestThrottle])
def update_manifest(request):
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    if not settings.DEBUG and not settings.DEVICE_UPDATE_ROLLOUT_ENABLED:
        return Response({"update_available": False, "reason": "release_authenticity_not_verified"})
    release = available_release_for(device)
    if not release:
        return Response({"update_available": False})
    with transaction.atomic():
        # Follow staff rollback's release -> device lock order.
        release = SoftwareRelease.objects.select_for_update().get(pk=release.pk)
        device = lock_authenticated_device(device, request.auth)
        if device.install_state != Device.InstallState.IDLE:
            return Response({"update_available": False, "reason": "device_not_eligible"})
        if release.status != SoftwareRelease.Status.PUBLISHED or available_release_for(device) != release:
            return Response({"update_available": False})
        assignment, _ = UpdateAssignment.objects.get_or_create(release=release, device=device)
        if assignment.state != UpdateAssignment.State.AVAILABLE:
            return Response({"update_available": False})
    return Response({
        "update_available": True,
        "version": release.version,
        "sha256": release.sha256,
        "release_notes": release.release_notes,
        "package_url": release.package_url,
    })


@api_view(["POST"])
@authentication_classes([DeviceTokenAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([DeviceUpdateResultThrottle])
def update_result(request):
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    serializer = UpdateResultSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    return Response(record_update_result(device, request.auth, data))
