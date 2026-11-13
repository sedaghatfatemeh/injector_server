from django.core.management.base import BaseCommand, CommandError

from devices.authentication import issue_device_token
from devices.models import AuditEntry, Device


class Command(BaseCommand):
    help = "Issue or rotate the one-time bearer credential for a registered device."

    def add_arguments(self, parser):
        parser.add_argument("serial_number")

    def handle(self, *args, **options):
        try:
            device = Device.objects.get(serial_number=options["serial_number"], is_archived=False)
        except Device.DoesNotExist as exc:
            raise CommandError("No active device found with that serial number.") from exc
        token = issue_device_token(device)
        AuditEntry.objects.create(
            actor=None,
            action="device.credential_rotated",
            target_type="device",
            target_id=str(device.pk),
            details={"serial_number": device.serial_number, "source": "management_command"},
        )
        self.stdout.write(self.style.SUCCESS(f"Device credential for {device.serial_number} (shown once):"))
        self.stdout.write(token)
