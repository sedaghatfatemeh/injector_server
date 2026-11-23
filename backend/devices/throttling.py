from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle

from .models import AuditEntry, StaffLoginThrottleBucket


class LoginThrottle(SimpleRateThrottle):
    scope = "login"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]

    def allow_request(self, request, view):
        if self.rate is None:
            return True
        key = salted_hmac("staff-login-throttle", str(self.get_ident(request)), algorithm="sha256").hexdigest()
        now = timezone.now()
        with transaction.atomic():
            bucket, _ = StaffLoginThrottleBucket.objects.select_for_update().get_or_create(
                key=key, defaults={"window_started_at": now},
            )
            elapsed = (now - bucket.window_started_at).total_seconds()
            if elapsed >= self.duration:
                bucket.window_started_at = now
                bucket.attempt_count = 0
                elapsed = 0
            self.retry_after = max(1, self.duration - elapsed)
            if bucket.attempt_count >= self.num_requests:
                allowed = False
            else:
                bucket.attempt_count += 1
                bucket.save(update_fields=["window_started_at", "attempt_count"])
                allowed = True
        if not allowed:
            AuditEntry.objects.create(action="staff.sign_in_throttled", target_type="user", target_id="", outcome="denied")
        return allowed

    def wait(self):
        return self.retry_after


class DeviceRateThrottle(UserRateThrottle):
    """Separate each device endpoint's allowance from staff and other devices."""

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]


class DeviceCheckInThrottle(DeviceRateThrottle):
    scope = "device_check_in"


class DeviceEventsThrottle(DeviceRateThrottle):
    scope = "device_events"


class DeviceManifestThrottle(DeviceRateThrottle):
    scope = "device_manifest"


class DeviceUpdateResultThrottle(DeviceRateThrottle):
    scope = "device_update_result"
