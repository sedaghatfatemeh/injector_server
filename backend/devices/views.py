from datetime import timedelta
from django.conf import settings

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from packaging.version import InvalidVersion, Version
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .authentication import DeviceTokenAuthentication
from .models import AuditEntry, Customer, Device, DeviceEvent, DeviceFault, SoftwareRelease, UpdateAssignment
from .permissions import IsSuperAdministrator
from .serializers import CheckInSerializer, CustomerSerializer, DeviceSerializer, EventIngestSerializer, EventSerializer, ReleaseSerializer, UpdateAssignmentSerializer, UpdateResultSerializer


class LoginThrottle(AnonRateThrottle):
    scope = "login"
    rate = "10/minute"


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser]
    search_fields = ["organization_name", "contact_name", "contact_email", "contact_phone"]
    filterset_fields = ["is_archived"]
    ordering_fields = ["organization_name", "created_at"]

    def get_queryset(self):
        return Customer.objects.annotate(device_count=Count("devices", filter=Q(devices__is_archived=False)))

    def perform_create(self, serializer):
        customer = serializer.save()
        AuditEntry.objects.create(actor=self.request.user, action="customer.created", target_type="customer", target_id=str(customer.pk))

    def perform_update(self, serializer):
        customer = serializer.save()
        AuditEntry.objects.create(actor=self.request.user, action="customer.updated", target_type="customer", target_id=str(customer.pk))

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSuperAdministrator()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=["is_archived", "updated_at"])
        AuditEntry.objects.create(actor=self.request.user, action="customer.archived", target_type="customer", target_id=str(instance.pk))


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = [IsAdminUser]
    search_fields = ["serial_number", "model_name", "customer__organization_name"]
    filterset_fields = ["customer", "model_name", "is_archived"]
    ordering_fields = ["serial_number", "model_name", "last_seen_at", "created_at"]

    def get_queryset(self):
        now = timezone.now()
        online_since = now - timedelta(minutes=settings.DEVICE_ONLINE_WINDOW_MINUTES)
        return Device.objects.select_related("customer").annotate(
            is_online=Count("id", filter=Q(last_seen_at__gte=online_since))
        ).annotate(
            active_fault_count=Count("faults", filter=Q(faults__state=DeviceEvent.State.ACTIVE), distinct=True)
        )

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
        device = serializer.save()
        AuditEntry.objects.create(actor=self.request.user, action="device.registered", target_type="device", target_id=str(device.pk), details={"serial_number": device.serial_number})

    def perform_update(self, serializer):
        device = serializer.save()
        AuditEntry.objects.create(actor=self.request.user, action="device.updated", target_type="device", target_id=str(device.pk), details={"serial_number": device.serial_number})

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=["is_archived", "updated_at"])
        AuditEntry.objects.create(actor=self.request.user, action="device.archived", target_type="device", target_id=str(instance.pk))

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        device = self.get_object()
        page = self.paginate_queryset(device.events.all())
        serializer = EventSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def updates(self, request, pk=None):
        device = self.get_object()
        page = self.paginate_queryset(device.update_assignments.select_related("release"))
        return self.get_paginated_response(UpdateAssignmentSerializer(page, many=True).data)


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ["device", "device__customer", "code", "state"]
    search_fields = ["device__serial_number", "device__customer__organization_name", "code", "summary"]
    ordering_fields = ["occurred_at", "received_at", "code"]

    def get_queryset(self):
        queryset = DeviceEvent.objects.select_related("device", "device__customer")
        start = self.request.query_params.get("occurred_after")
        end = self.request.query_params.get("occurred_before")
        if start:
            queryset = queryset.filter(occurred_at__gte=start)
        if end:
            queryset = queryset.filter(occurred_at__lte=end)
        return queryset


class ReleaseViewSet(viewsets.ModelViewSet):
    serializer_class = ReleaseSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return SoftwareRelease.objects.all()

    def get_permissions(self):
        if self.action in {"create", "withdraw"}:
            return [IsSuperAdministrator()]
        return super().get_permissions()

    def perform_create(self, serializer):
        targets = serializer.validated_data.get("target_devices", [])
        target_all = serializer.validated_data.get("target_all_devices", False)
        if target_all == bool(targets):
            raise ValidationError("Choose either all compatible devices or a non-empty list of selected devices.")
        if any(device.is_archived for device in targets):
            raise ValidationError({"target_devices": "Archived devices cannot receive releases."})
        release = serializer.save(
            created_by=self.request.user,
            status=SoftwareRelease.Status.PUBLISHED,
            published_at=timezone.now(),
            target_all_devices=target_all,
        )
        devices = Device.objects.filter(is_archived=False) if target_all else release.target_devices.filter(is_archived=False)
        if release.compatible_models:
            compatible = devices.filter(model_name__in=release.compatible_models)
            if not target_all and compatible.count() != devices.count():
                release.delete()
                raise ValidationError({"target_devices": "Every selected device must match a compatible model."})
            devices = compatible
        UpdateAssignment.objects.bulk_create(
            [UpdateAssignment(release=release, device=device) for device in devices],
            ignore_conflicts=True,
        )
        AuditEntry.objects.create(
            actor=self.request.user,
            action="release.published_automatically",
            target_type="release",
            target_id=str(release.pk),
            details={"version": release.version, "device_count": devices.count()},
        )

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        release = self.get_object()
        if release.status != SoftwareRelease.Status.PUBLISHED:
            raise ValidationError({"status": "Only a published release can be withdrawn."})
        release.status = SoftwareRelease.Status.WITHDRAWN
        release.save(update_fields=["status"])
        AuditEntry.objects.create(actor=request.user, action="release.withdrawn", target_type="release", target_id=str(release.pk))
        return Response(self.get_serializer(release).data)

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        release = self.get_object()
        if release.status != SoftwareRelease.Status.PUBLISHED:
            raise ValidationError({"release": "Only a published, retained release can be assigned for rollback."})
        device_ids = request.data.get("device_ids")
        reason = request.data.get("reason", "")
        if not isinstance(device_ids, list) or not device_ids or not isinstance(reason, str) or not reason.strip():
            raise ValidationError("Provide one or more device_ids and a rollback reason.")
        devices = list(Device.objects.filter(pk__in=device_ids, is_archived=False).select_related("customer"))
        if len(devices) != len(set(device_ids)):
            raise ValidationError({"device_ids": "One or more devices do not exist or are archived."})
        for device in devices:
            if release.compatible_models and device.model_name not in release.compatible_models:
                raise ValidationError({"device_ids": f"Device {device.serial_number} is incompatible with this release."})
            if not release_is_eligible(device, release, allow_downgrade=True):
                raise ValidationError({"device_ids": f"Release {release.version} is not a valid rollback target for {device.serial_number}."})
        for device in devices:
            UpdateAssignment.objects.update_or_create(
                release=release,
                device=device,
                defaults={"allow_downgrade": True, "state": UpdateAssignment.State.AVAILABLE, "result_code": ""},
            )
        AuditEntry.objects.create(
            actor=request.user,
            action="release.rollback_assigned",
            target_type="release",
            target_id=str(release.pk),
            details={"version": release.version, "device_serials": [d.serial_number for d in devices], "reason": reason.strip()},
        )
        return Response({"release_version": release.version, "assigned_devices": [d.serial_number for d in devices]})

    @action(detail=False, methods=["get"], url_path="assignments")
    def assignments(self, request):
        qs = UpdateAssignment.objects.select_related("device", "release")
        device = request.query_params.get("device")
        if device:
            qs = qs.filter(device__serial_number=device)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(UpdateAssignmentSerializer(page, many=True).data)


def release_is_eligible(device, release, allow_downgrade=False):
    if not device.software_version:
        return not release.minimum_version
    try:
        current = Version(device.software_version.removeprefix("v"))
        target = Version(release.version.removeprefix("v"))
        minimum = Version(release.minimum_version.removeprefix("v")) if release.minimum_version else None
    except InvalidVersion:
        return False
    version_match = target < current if allow_downgrade else target > current
    return version_match and (minimum is None or current >= minimum)


def available_release_for(device):
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
    if device.is_archived:
        return None
    releases = releases.filter(Q(compatible_models=[]) | Q(compatible_models__contains=[device.model_name]))
    for release in releases.distinct().order_by("-published_at"):
        assignment = UpdateAssignment.objects.filter(release=release, device=device).first()
        if assignment is None or (assignment.state == UpdateAssignment.State.AVAILABLE and not assignment.allow_downgrade):
            if release_is_eligible(device, release):
                return release
    return None


def event_matches_payload(event, device, data):
    return (
        event.code == data["code"]
        and event.summary == data["summary"]
        and event.occurred_at == data["occurred_at"]
        and event.fault_id == data.get("fault_id")
        and event.state == data["state"]
        and (not data["software_version"] or event.software_version == data["software_version"])
        and event.metadata == data["metadata"]
    )


@api_view(["POST"])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def staff_login(request):
    email = request.data.get("email", "")
    password = request.data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        raise AuthenticationFailed("Email or password is incorrect.")
    email = email.strip().lower()
    User = get_user_model()
    matching_users = User.objects.filter(email__iexact=email, is_active=True)
    if matching_users.count() != 1:
        raise AuthenticationFailed("Email or password is incorrect.")
    user_record = matching_users.first()
    user = authenticate(request, username=user_record.get_username(), password=password) if user_record and password else None
    if not user or not user.is_staff:
        raise AuthenticationFailed("Email or password is incorrect.")
    token, _ = Token.objects.get_or_create(user=user)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    AuditEntry.objects.create(actor=user, action="staff.signed_in", target_type="user", target_id=str(user.pk))
    return Response({"token": token.key, "email": user.email, "role": "super_admin" if user.is_superuser else "support"})


@api_view(["POST"])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def staff_logout(request):
    if isinstance(request.auth, Token):
        request.auth.delete()
    AuditEntry.objects.create(actor=request.user, action="staff.signed_out", target_type="user", target_id=str(request.user.pk))
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAdminUser])
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
def device_check_in(request):
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    serializer = CheckInSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    device.software_version = serializer.validated_data["software_version"]
    device.install_state = serializer.validated_data["install_state"]
    device.last_seen_at = timezone.now()
    device.save(update_fields=["software_version", "install_state", "last_seen_at", "updated_at"])
    update_available = device.install_state == Device.InstallState.IDLE and available_release_for(device) is not None
    return Response({"accepted": True, "server_time": device.last_seen_at, "update_available": update_available})


@api_view(["POST"])
@authentication_classes([DeviceTokenAuthentication])
@permission_classes([IsAuthenticated])
def ingest_events(request):
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    raw_events = request.data.get("events")
    if not isinstance(raw_events, list) or not raw_events or len(raw_events) > 200:
        raise ValidationError({"events": "Provide between 1 and 200 events per batch."})
    results = []
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at", "updated_at"])
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            results.append({"event_id": None, "status": "rejected", "errors": {"event": ["Each event must be a JSON object."]}})
            continue
        serializer = EventIngestSerializer(data=raw_event)
        if not serializer.is_valid():
            results.append({"event_id": raw_event.get("event_id"), "status": "rejected", "errors": serializer.errors})
            continue
        data = serializer.validated_data
        try:
            with transaction.atomic():
                event, created = DeviceEvent.objects.get_or_create(
                    device=device,
                    event_id=data["event_id"],
                    defaults={**data, "software_version": data["software_version"] or device.software_version},
                )
            if created:
                if data["state"] in {DeviceEvent.State.ACTIVE, DeviceEvent.State.RESOLVED}:
                    fault, fault_created = DeviceFault.objects.get_or_create(
                        device=device,
                        fault_id=data["fault_id"],
                        defaults={
                            "latest_event": event,
                            "code": data["code"],
                            "summary": data["summary"],
                            "state": data["state"],
                            "started_at": data["occurred_at"],
                        },
                    )
                    if not fault_created:
                        changed = []
                        if data["state"] == DeviceEvent.State.ACTIVE and event.occurred_at < fault.started_at:
                            fault.started_at = event.occurred_at
                            changed.append("started_at")
                        if event.occurred_at >= fault.latest_event.occurred_at:
                            fault.latest_event = event
                            fault.code = data["code"]
                            fault.summary = data["summary"]
                            fault.state = data["state"]
                            changed.extend(["latest_event", "code", "summary", "state"])
                        if changed:
                            fault.save(update_fields=[*changed, "updated_at"])
                results.append({"event_id": str(event.event_id), "status": "accepted"})
            elif event_matches_payload(event, device, data):
                results.append({"event_id": str(event.event_id), "status": "duplicate"})
            else:
                results.append({"event_id": str(event.event_id), "status": "rejected", "errors": {"event_id": ["This ID was already used for a different event."]}})
        except IntegrityError:
            existing = DeviceEvent.objects.filter(device=device, event_id=data["event_id"]).first()
            if existing and event_matches_payload(existing, device, data):
                results.append({"event_id": str(data["event_id"]), "status": "duplicate"})
            else:
                results.append({"event_id": str(data["event_id"]), "status": "rejected", "errors": {"event_id": ["This ID was already used for a different event."]}})
    return Response({"results": results}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([DeviceTokenAuthentication])
@permission_classes([IsAuthenticated])
def update_manifest(request):
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    release = available_release_for(device)
    if not release:
        return Response({"update_available": False})
    if device.install_state != Device.InstallState.IDLE:
        return Response({"update_available": False, "reason": "device_not_eligible"})
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
def update_result(request):
    device = request.user
    if not isinstance(device, Device):
        raise AuthenticationFailed("A device credential is required.")
    serializer = UpdateResultSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    assignment = UpdateAssignment.objects.select_related("release").filter(device=device, release__version=data["release_version"]).first()
    if not assignment:
        raise ValidationError({"release_version": "No update assignment exists for this release."})
    if data["state"] not in {UpdateAssignment.State.SUCCEEDED, UpdateAssignment.State.FAILED, UpdateAssignment.State.ROLLED_BACK} and device.install_state != Device.InstallState.IDLE:
        raise ValidationError({"state": "The device must report idle before continuing installation."})
    assignment.state = data["state"]
    assignment.result_code = data["result_code"]
    assignment.save(update_fields=["state", "result_code", "updated_at"])
    if data["state"] == UpdateAssignment.State.SUCCEEDED:
        device.software_version = data["release_version"]
        device.save(update_fields=["software_version", "updated_at"])
    AuditEntry.objects.create(actor=None, action=f"device.update.{data['state']}", target_type="device", target_id=str(device.pk), details={"release_version": data["release_version"], "result_code": data["result_code"]})
    return Response({"accepted": True})
