from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from devices.models import StaffLoginThrottleBucket


class Command(BaseCommand):
    help = "Remove login rate-limit buckets last started more than seven days ago."

    def handle(self, *args, **options):
        deleted, _ = StaffLoginThrottleBucket.objects.filter(
            window_started_at__lt=timezone.now() - timedelta(days=7),
        ).delete()
        self.stdout.write(f"Removed {deleted} expired login throttle buckets.")
