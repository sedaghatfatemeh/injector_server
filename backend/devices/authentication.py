import hashlib
import secrets

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import DeviceCredential


def digest_device_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_device_token(device):
    raw_token = secrets.token_urlsafe(40)
    DeviceCredential.objects.update_or_create(
        device=device,
        defaults={"token_digest": digest_device_token(raw_token), "revoked_at": None},
    )
    return raw_token


class DeviceTokenAuthentication(BaseAuthentication):
    """Authenticate device requests with a revocable, per-device bearer token."""

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"device":
            return None
        if len(header) != 2:
            raise AuthenticationFailed("Invalid device authorization header.")
        try:
            credential = DeviceCredential.objects.select_related("device").get(
                token_digest=digest_device_token(header[1].decode("utf-8")), revoked_at__isnull=True
            )
        except (DeviceCredential.DoesNotExist, UnicodeDecodeError):
            raise AuthenticationFailed("Invalid or revoked device credential.")
        if credential.device.is_archived:
            raise AuthenticationFailed("This device is archived.")
        return credential.device, credential
