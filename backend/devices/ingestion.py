import uuid

from django.db import transaction

from .authentication import lock_authenticated_device
from .models import AuditEntry, DeviceEvent, DeviceFault


def safe_event_id(raw_event):
    """Never copy arbitrary rejected payload values into responses or audits."""
    value = raw_event.get("event_id") if isinstance(raw_event, dict) else None
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def event_matches_payload(event, data):
    return (
        event.code == data["code"]
        and event.summary == data["summary"]
        and event.occurred_at == data["occurred_at"]
        and event.fault_id == data.get("fault_id")
        and event.state == data["state"]
        and (not data["software_version"] or event.software_version == data["software_version"])
        and event.metadata == data["metadata"]
    )


def project_fault(event):
    if event.state not in {DeviceEvent.State.ACTIVE, DeviceEvent.State.RESOLVED}:
        return
    fault, created = DeviceFault.objects.get_or_create(
        device=event.device, fault_id=event.fault_id,
        defaults={"latest_event": event, "code": event.code, "summary": event.summary,
                  "state": event.state, "started_at": event.occurred_at},
    )
    if created:
        return
    changed = []
    if event.state == DeviceEvent.State.ACTIVE and event.occurred_at < fault.started_at:
        fault.started_at = event.occurred_at
        changed.append("started_at")
    if (event.occurred_at, event.event_id) > (fault.latest_event.occurred_at, fault.latest_event.event_id):
        fault.latest_event = event
        fault.code = event.code
        fault.summary = event.summary
        fault.state = event.state
        changed.extend(["latest_event", "code", "summary", "state"])
    if changed:
        fault.save(update_fields=[*changed, "updated_at"])


def ingest_event(device, credential, data, received_at):
    """One event, its fault projection and communication freshness commit together.

    Device row locking serializes concurrent batches with credential lifecycle
    changes. Earlier events may commit before a later event fails; clients retry
    all unacknowledged stable IDs and receive duplicates for committed facts.
    """
    with transaction.atomic():
        device = lock_authenticated_device(device, credential)
        event, created = DeviceEvent.objects.get_or_create(
            device=device, event_id=data["event_id"],
            defaults={**data, "software_version": data["software_version"] or device.software_version,
                      "received_at": received_at},
        )
        if created:
            project_fault(event)
            outcome = "accepted"
        elif event_matches_payload(event, data):
            outcome = "duplicate"
        else:
            AuditEntry.objects.create(
                action="device.event_id_conflict", target_type="device", target_id=str(device.pk),
                outcome="rejected", details={"event_id": str(event.event_id)},
            )
            return {"event_id": str(event.event_id), "status": "rejected",
                    "errors": {"event_id": ["This ID was already used for a different event."]}}
        if device.last_seen_at is None or device.last_seen_at < received_at:
            device.last_seen_at = received_at
            device.save(update_fields=["last_seen_at", "updated_at"])
        return {"event_id": str(event.event_id), "status": outcome}
