from django.core.management.base import BaseCommand, CommandError

from devices.authentication import revoke_device_token
from devices.models import Device


class Command(BaseCommand):
    help = "Revoke a device credential without issuing a replacement."

    def add_arguments(self, parser):
        parser.add_argument("serial_number")

    def handle(self, *args, **options):
        try:
            device = Device.objects.get(serial_number=options["serial_number"])
        except Device.DoesNotExist as exc:
            raise CommandError("No device found with that serial number.") from exc
        changed = revoke_device_token(device, source="management_command")
        self.stdout.write("Device credential revoked." if changed else "No active device credential to revoke.")
