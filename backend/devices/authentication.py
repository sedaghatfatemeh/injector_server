import hashlib
import secrets

from django.db import transaction
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import AuditEntry, Device, DeviceCredential


def digest_device_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_device_token(device, *, actor=None, source="internal"):
    raw_token = secrets.token_urlsafe(40)
    with transaction.atomic():
        locked = Device.objects.select_for_update().get(pk=device.pk)
        if locked.is_archived:
            raise ValueError("Credentials cannot be issued for an archived device.")
        DeviceCredential.objects.update_or_create(
            device=device,
            defaults={"token_digest": digest_device_token(raw_token), "revoked_at": None},
        )
        AuditEntry.objects.create(
            actor=actor, action="device.credential_rotated", target_type="device", target_id=str(device.pk),
            details={"serial_number": locked.serial_number, "source": source},
        )
    return raw_token


def revoke_device_token(device, *, actor=None, source="internal"):
    with transaction.atomic():
        locked = Device.objects.select_for_update().get(pk=device.pk)
        changed = DeviceCredential.objects.filter(device=locked, revoked_at__isnull=True).update(revoked_at=timezone.now())
        if changed:
            AuditEntry.objects.create(
                actor=actor, action="device.credential_revoked", target_type="device", target_id=str(device.pk),
                details={"serial_number": locked.serial_number, "source": source},
            )
        return bool(changed)


def lock_authenticated_device(device, credential):
    """Call inside a transaction to serialize check-in with rotation/revocation."""
    locked = Device.objects.select_for_update().get(pk=device.pk)
    if locked.is_archived or not DeviceCredential.objects.filter(
        device=locked, pk=credential.pk, token_digest=credential.token_digest, revoked_at__isnull=True,
    ).exists():
        raise AuthenticationFailed("Invalid or revoked device credential.")
    return locked


class DeviceTokenAuthentication(BaseAuthentication):
    """Authenticate device requests with a revocable, per-device bearer token."""

    def authenticate_header(self, request):
        return "Device"

    def authenticate(self, request):
        try:
            header = get_authorization_header(request).split()
        except UnicodeError as exc:
            raise AuthenticationFailed("Invalid device authorization header.") from exc
        if not header or header[0].lower() != b"device":
            return None
        if len(header) != 2 or len(header[1]) > 512:
            raise AuthenticationFailed("Invalid device authorization header.")
        try:
            credential = DeviceCredential.objects.select_related("device").get(
                token_digest=digest_device_token(header[1].decode("utf-8")), revoked_at__isnull=True
            )
        except (DeviceCredential.DoesNotExist, UnicodeDecodeError):
            raise AuthenticationFailed("Invalid or revoked device credential.")
        if credential.device.is_archived:
            raise AuthenticationFailed("Invalid or revoked device credential.")
        return credential.device, credential
