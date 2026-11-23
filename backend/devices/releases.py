"""Device-reported update lifecycle; all mutations commit with their audit."""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .authentication import lock_authenticated_device
from .models import AuditEntry, Device, UpdateAssignment


TERMINAL_STATES = {
    UpdateAssignment.State.SUCCEEDED, UpdateAssignment.State.FAILED, UpdateAssignment.State.ROLLED_BACK,
}
ALLOWED_NEXT = {
    UpdateAssignment.State.AVAILABLE: {
        UpdateAssignment.State.DOWNLOADING, UpdateAssignment.State.DOWNLOADED, UpdateAssignment.State.FAILED,
    },
    UpdateAssignment.State.DOWNLOADING: {UpdateAssignment.State.DOWNLOADED, UpdateAssignment.State.FAILED},
    UpdateAssignment.State.DOWNLOADED: {UpdateAssignment.State.INSTALLING, UpdateAssignment.State.FAILED},
    UpdateAssignment.State.INSTALLING: TERMINAL_STATES,
}


def record_update_result(device, credential, data):
    received_at = timezone.now()
    with transaction.atomic():
        device = lock_authenticated_device(device, credential)
        # The version filter joins releases; lock only the assignment to avoid
        # reversing the release -> device order used by staff actions.
        assignment = UpdateAssignment.objects.select_for_update(of=("self",)).filter(
            device=device, release__version=data["release_version"],
        ).first()
        if assignment is None:
            raise ValidationError({"release_version": "No update assignment exists for this release."})
        reported_at = data.get("reported_at", received_at)
        details = {
            "release_version": data["release_version"], "result_code": data["result_code"],
            "state": data["state"], "reported_at": reported_at.isoformat(),
            "received_at": received_at.isoformat(),
        }
        if assignment.reported_at and reported_at < assignment.reported_at:
            AuditEntry.objects.create(
                action="device.update.stale_report", target_type="device", target_id=str(device.pk),
                outcome="ignored", details=details,
            )
            return {"accepted": True, "stale": True}
        if assignment.state == data["state"]:
            if assignment.result_code == data["result_code"]:
                return {"accepted": True, "duplicate": True}
            # No submitted payload or secret-bearing text is included in errors.
            raise ValidationError({"state": "A repeated state must retain the original result code."})
        if assignment.reported_at and reported_at == assignment.reported_at:
            raise ValidationError({"reported_at": "Conflicting reports must not share a timestamp."})
        if data["state"] not in ALLOWED_NEXT.get(assignment.state, set()):
            raise ValidationError({"state": "The requested update lifecycle transition is invalid."})
        if data["state"] == UpdateAssignment.State.INSTALLING and device.install_state != Device.InstallState.IDLE:
            raise ValidationError({"state": "The device must report idle before installation starts."})
        assignment.state = data["state"]
        assignment.result_code = data["result_code"]
        assignment.reported_at = reported_at
        assignment.report_received_at = received_at
        assignment.save(update_fields=["state", "result_code", "reported_at", "report_received_at", "updated_at"])
        # A delayed outcome must never replace a more recent check-in's version.
        if data["state"] == UpdateAssignment.State.SUCCEEDED and (
            not device.last_seen_at or reported_at >= device.last_seen_at
        ):
            device.software_version = data["release_version"]
            device.save(update_fields=["software_version", "updated_at"])
        AuditEntry.objects.create(
            action=f"device.update.{data['state']}", target_type="device", target_id=str(device.pk), details=details,
        )
        return {"accepted": True}
