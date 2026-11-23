from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone as datetime_timezone
from threading import Barrier
from unittest.mock import patch
import json
import uuid

import pytest
from django.core.cache import cache
from django.db import IntegrityError, connections
from django.utils import timezone
from rest_framework.test import APIClient

from devices import ingestion
from devices.authentication import revoke_device_token
from devices.models import AuditEntry, Device, DeviceFault
from devices.serializers import EventIngestSerializer
from .test_api import device_client, device_pair, event_payload


pytestmark = pytest.mark.django_db
URL = "/api/v1/device/events/"


@pytest.fixture(autouse=True)
def clear_throttles():
    cache.clear()


def deliver(client, events):
    return client.post(URL, {"events": events}, format="json")


def outcomes(response):
    assert response.status_code == 200
    return [item["status"] for item in response.data["results"]]


@pytest.mark.parametrize("payload", [None, [], "bad", 1, {}, {"events": []}, {"events": {}},
                                        {"events": None}, {"events": [], "device": 1}, {"events": [], "\ud800": 1}])
def test_invalid_envelope_is_rejected_without_storing_or_refreshing(payload):
    device, token = device_pair()
    body = json.dumps(payload).encode()
    response = device_client(token).generic("POST", URL, body, content_type="application/json")
    assert response.status_code == 400
    device.refresh_from_db()
    assert not device.events.exists() and device.last_seen_at is None


@pytest.mark.parametrize("body,content_type,expected", [
    (b"{", "application/json", 400),
    (b"[" * 1200 + b"]" * 1200, "application/json", 400),
    (b"events=[]", "application/x-www-form-urlencoded", 415),
    ("{}".encode("utf-16"), "application/json; charset=utf-16", 400),
])
def test_malformed_batch_body_fails_as_client_error(body, content_type, expected):
    device, token = device_pair()
    assert device_client(token).generic("POST", URL, body, content_type=content_type).status_code == expected
    device.refresh_from_db()
    assert device.last_seen_at is None and device.events.count() == 0


def test_batch_count_and_body_byte_limits_are_configurable(settings):
    device, token = device_pair()
    client = device_client(token)
    settings.DEVICE_EVENT_BATCH_MAX = 2
    assert deliver(client, [event_payload() for _ in range(3)]).status_code == 400
    settings.DEVICE_EVENT_BATCH_MAX_BYTES = 8
    assert client.generic("POST", URL, b'{"events":[]}', content_type="application/json").status_code == 413
    settings.DEVICE_EVENT_BATCH_MAX_BYTES = 4096
    assert outcomes(deliver(client, [event_payload(), event_payload()])) == ["accepted", "accepted"]
    assert device.events.count() == 2


@pytest.mark.parametrize("changes", [
    {"occurred_at": "2026-01-01T10:00:00"}, {"occurred_at": "not-a-date"},
    {"occurred_at": "2099-01-01T00:00:00Z"}, {"event_id": 1}, {"fault_id": 1},
    {"code": 12}, {"code": "INVALID CODE"}, {"summary": 12}, {"software_version": 12},
    {"received_at": "2026-01-01T00:00:00Z"}, {"device": 999},
    {"state": "active", "fault_id": None}, {"state": "invalid"},
    {"metadata": []}, {"metadata": {"value": "\x00"}}, {"metadata": {"\x00": "value"}},
    {"metadata": {"value": "\ud800"}},
    {"\ud800": "unknown_field"}, {"state": "\ud800"}, {"summary": "\ud800"}, {"software_version": "\ud800"},
])
def test_invalid_event_has_per_item_rejection_without_changing_freshness(changes):
    device, token = device_pair()
    payload = {**event_payload(), **changes}
    # ASCII escapes allow malformed Unicode input to reach the actual JSON parser.
    body = json.dumps({"events": [payload]}).encode()
    response = device_client(token).generic("POST", URL, body, content_type="application/json")
    assert outcomes(response) == ["rejected"]
    device.refresh_from_db()
    assert not device.events.exists() and device.last_seen_at is None
    assert AuditEntry.objects.filter(action="device.event_rejected", outcome="rejected").exists()


def test_metadata_numeric_overflow_is_rejected_before_postgres():
    device, token = device_pair()
    payload = event_payload()
    payload["metadata"] = {"number": "OVERFLOW"}
    body = json.dumps({"events": [payload]}).replace('"OVERFLOW"', "1e400").encode()
    assert outcomes(device_client(token).generic("POST", URL, body, content_type="application/json")) == ["rejected"]
    assert not device.events.exists()


def test_metadata_byte_size_counts_utf8_and_depth_limits_containers(settings):
    device, token = device_pair()
    client = device_client(token)
    payload = event_payload()
    payload["metadata"] = {"name": "شرق"}
    size = len(json.dumps(payload["metadata"], ensure_ascii=False, separators=(",", ":")).encode())
    settings.DEVICE_EVENT_METADATA_MAX_BYTES = size - 1
    assert outcomes(deliver(client, [payload])) == ["rejected"]
    settings.DEVICE_EVENT_METADATA_MAX_BYTES = size
    assert outcomes(deliver(client, [payload])) == ["accepted"]
    settings.DEVICE_EVENT_METADATA_MAX_BYTES = 16384
    settings.DEVICE_EVENT_METADATA_MAX_DEPTH = 3
    shallow, deep = event_payload(), event_payload()
    shallow["metadata"] = {"a": [{"b": 1}]}
    deep["metadata"] = {"a": [{"b": []}]}
    assert outcomes(deliver(client, [shallow, deep])) == ["accepted", "rejected"]


def test_future_skew_boundary_and_server_receipt_time_are_independent(settings):
    device, token = device_pair()
    now = timezone.now()
    settings.DEVICE_EVENT_FUTURE_SKEW_SECONDS = 5
    valid = event_payload(occurred_at=now + timedelta(seconds=5))
    invalid = event_payload(occurred_at=now + timedelta(seconds=5, microseconds=1))
    with patch("devices.views.timezone.now", return_value=now):
        response = deliver(device_client(token), [valid, invalid])
    assert outcomes(response) == ["accepted", "rejected"]
    event = device.events.get()
    device.refresh_from_db()
    assert event.received_at == device.last_seen_at == now
    assert event.occurred_at == now + timedelta(seconds=5)


def test_mixed_results_are_ordered_and_invalid_payloads_are_not_echoed_or_audited_raw():
    device, token = device_pair()
    client = device_client(token)
    valid = event_payload()
    secret = "private-device-credential-do-not-echo"
    malformed = {**event_payload(), "event_id": secret, "metadata": {"credential": secret}}
    conflict = {**valid, "code": "OTHER"}
    response = deliver(client, [valid, valid, malformed, conflict, secret, event_payload()])
    assert outcomes(response) == ["accepted", "duplicate", "rejected", "rejected", "rejected", "accepted"]
    assert response.data["results"][2]["event_id"] is None
    assert response.data["results"][4]["event_id"] is None
    assert secret not in str(response.data)
    assert secret not in str(list(AuditEntry.objects.values("details")))
    assert device.events.count() == 2


def test_batch_receipt_time_is_shared_and_retries_preserve_original_facts():
    device, token = device_pair(version="1.0.0")
    client = device_client(token)
    first, second = event_payload(), event_payload()
    assert outcomes(deliver(client, [first, second])) == ["accepted", "accepted"]
    records = list(device.events.order_by("id"))
    assert records[0].received_at == records[1].received_at
    original = records[0].received_at
    Device.objects.filter(pk=device.pk).update(software_version="2.0.0")
    equivalent = {**first, "occurred_at": records[0].occurred_at.astimezone(
        datetime_timezone(timedelta(hours=3, minutes=30))).isoformat()}
    assert outcomes(deliver(client, [equivalent])) == ["duplicate"]
    records[0].refresh_from_db()
    assert records[0].received_at == original and records[0].software_version == "1.0.0"
    assert outcomes(deliver(client, [{**first, "software_version": "2.0.0"}])) == ["rejected"]


@pytest.mark.parametrize("reverse", [False, True])
def test_equal_occurrence_time_uses_uuid_tie_break_in_both_delivery_orders(reverse):
    device, token = device_pair()
    fault = uuid.uuid4()
    now = timezone.now() - timedelta(days=1)
    lower = event_payload(event_id=uuid.UUID(int=1), fault_id=fault, state="active", occurred_at=now)
    higher = event_payload(event_id=uuid.UUID(int=2), fault_id=fault, state="resolved", occurred_at=now)
    sequence = [higher, lower] if reverse else [lower, higher]
    assert outcomes(deliver(device_client(token), sequence)) == ["accepted", "accepted"]
    current = DeviceFault.objects.get(device=device, fault_id=fault)
    assert current.state == "resolved" and current.latest_event.event_id == uuid.UUID(int=2)
    assert device.events.count() == 2


def test_later_storage_failure_keeps_earlier_event_retryable_and_its_freshness_committed():
    device, token = device_pair()
    client = device_client(token)
    first, second, third = [event_payload(code=code) for code in ("FIRST", "SECOND", "THIRD")]
    original = ingestion.project_fault

    def fail_second(event):
        if event.code == "SECOND":
            raise IntegrityError("projection storage unavailable")
        return original(event)

    with patch("devices.ingestion.project_fault", side_effect=fail_second):
        with pytest.raises(IntegrityError, match="storage unavailable"):
            deliver(client, [first, second, third])
    assert device.events.count() == 1
    device.refresh_from_db()
    saved = device.events.get()
    original_receipt = saved.received_at
    assert device.last_seen_at == saved.received_at
    assert outcomes(deliver(client, [first, second, third])) == ["duplicate", "accepted", "accepted"]
    assert device.events.count() == 3
    saved.refresh_from_db()
    assert saved.received_at == original_receipt


def test_revocation_between_authentication_and_event_write_prevents_ingestion():
    device, token = device_pair()
    original = EventIngestSerializer.is_valid

    def validate_then_revoke(serializer, *args, **kwargs):
        result = original(serializer, *args, **kwargs)
        revoke_device_token(device)
        return result

    with patch.object(EventIngestSerializer, "is_valid", validate_then_revoke):
        response = deliver(device_client(token), [event_payload()])
    assert response.status_code == 401
    device.refresh_from_db()
    assert device.last_seen_at is None and not device.events.exists()


def test_serial_number_without_a_credential_cannot_submit_events():
    device, _ = device_pair()
    response = APIClient().post(URL, {"serial_number": device.serial_number, "events": [event_payload()]}, format="json")
    assert response.status_code == 401 and not device.events.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("conflicting", [False, True])
def test_concurrent_same_id_is_idempotent_or_conflicting_without_overwriting_facts(conflicting):
    device, token = device_pair()
    first = event_payload(code="FIRST")
    second = {**first, "code": "SECOND"} if conflicting else first
    barrier = Barrier(2)

    def send(payload):
        try:
            barrier.wait(timeout=10)
            response = deliver(device_client(token), [payload])
            assert response.status_code == 200
            return payload["code"], response.data["results"][0]["status"]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(send, [first, second]))
    assert sorted(status for _, status in results) == (["accepted", "rejected"] if conflicting else ["accepted", "duplicate"])
    assert device.events.count() == 1
    winner = next(code for code, status in results if status == "accepted")
    assert device.events.get().code == winner
