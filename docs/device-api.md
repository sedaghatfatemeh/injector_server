# Device identity and check-in contract (API v1)

This document describes the server contract under `/api/v1/`. Device-client source is not in this repository. The device owner must review payload compatibility and rollout order before installing a production client; the examples below are not an end-to-end device integration test. Unknown check-in fields, non-JSON requests, and oversized bodies are now rejected explicitly. Clients relying on those inputs need an agreed transition or a new API version before rollout.

## Identity and credential lifecycle

Every device endpoint requires `Authorization: Device <device-credential>`. A serial number in a payload does not authenticate or select a device. Staff browser sessions and browser bearer tokens do not authorize device check-ins. Use HTTPS outside the local development loopback environment.

Provision a registered, active device with either:

- Super-administrator `POST /api/v1/devices/{id}/provision_credential/` with the normal staff session and CSRF token. HTTP 201 returns `{"credential":"<one-time-secret>","shown_once":true}` with `Cache-Control: no-store`.
- `docker compose exec api python manage.py provision_device <serial>` from a trusted operator shell. Output contains the secret once; do not capture it in shared logs, tickets, screenshots or shell history.

Store that secret securely on the device. The server retains only its SHA-256 digest and cannot retrieve the plaintext later. Generated secrets use 40 random bytes encoded as URL-safe text. Authorization token input is limited to 512 bytes. Reprovisioning replaces the digest, invalidating the previous secret without changing the device identity.

Revoke without a replacement using super-administrator `POST /api/v1/devices/{id}/revoke_credential/` or `docker compose exec api python manage.py revoke_device_credential <serial>`. The API returns `{"revoked":true,"changed":true}`; repeating it returns `changed:false`. Archived devices cannot check in or receive new credentials. Their credential can still be revoked through the management command (or the staff endpoint with `?is_archived=true`).

Rotation and revocation serialize on the device row, and commit with a secret-free audit entry. Audit failure rolls the credential change back. Check-in and each valid event revalidate the credential under the same lock immediately before writing, so a token revoked or replaced after initial authentication cannot perform those writes after the credential change. Earlier committed events remain stored and follow the retry rules below.

## Check-in

`POST /api/v1/device/check-in/` accepts UTF-8 `application/json` with an object body. The default maximum is 4,096 bytes, including whitespace, configured by `DEVICE_CHECK_IN_MAX_BYTES`. The parser reads at most the configured limit plus one byte before rejecting an oversized body.

| Field | Type | Meaning |
| --- | --- | --- |
| `software_version` | Optional string, maximum 80 characters | Latest reported version. Omission preserves the previous version; an explicit empty string records an unknown version. |
| `install_state` | Optional `idle`, `testing` or `unknown` | Latest device-reported state. Omission preserves the previous report. |

No other fields are accepted. In particular, do not send a device ID, serial number or client timestamp here. Send both fields when reporting a current version/state; `{}` is a heartbeat that changes communication freshness only.

Request:

```json
{"software_version":"2.4.1","install_state":"testing"}
```

Successful HTTP 200 response:

```json
{"accepted":true,"server_time":"2026-11-15T10:00:00Z","update_available":false}
```

The server assigns receipt time in UTC. Only an authenticated, validated check-in advances its device's `last_seen_at`. A delayed/invalid request cannot move freshness backwards or change another device. If receipt time precedes an existing last-seen timestamp, the server acknowledges without overwriting newer stored facts.

`update_available` is an offer based on the last reported state and compatible release metadata. It is false when the device is not reported idle or production update rollout is gated off. The manifest endpoint is the authoritative next lookup. The device always makes the final safe-install decision; this API never controls or interrupts a test.

## Errors and retry

| HTTP status | Handling |
| --- | --- |
| 400 | Malformed JSON, invalid field/type/value, or excessive nesting. Correct the payload before retrying. Field errors identify rejected check-in keys; submitted secrets are not echoed. |
| 401 | Missing, malformed, invalid, revoked, replaced or archived-device credential. Stop sending with that credential and request authorized reprovisioning. |
| 413 | Check-in body exceeds its byte limit. Reduce the body before retrying. |
| 415 | Unsupported content type. Use `application/json`. |
| 429 | Endpoint allowance exhausted. Honor `Retry-After` and retry with backoff. |
| 5xx / transport failure | Retry with bounded exponential backoff and jitter. Event delivery additionally requires stable event IDs and acknowledgement handling. |

## Endpoint rate defaults

Allowances are separate per authenticated device and endpoint; one device does not consume another device's allowance.

| Endpoint | Configuration | Default |
| --- | --- | --- |
| `POST device/check-in/` | `DEVICE_CHECK_IN_RATE` | 60/minute |
| `POST device/events/` | `DEVICE_EVENTS_RATE` | 120/minute |
| `GET device/update-manifest/` | `DEVICE_MANIFEST_RATE` | 30/minute |
| `POST device/update-result/` | `DEVICE_UPDATE_RESULT_RATE` | 60/minute |

These DRF device throttles use Django's cache and are approximate under concurrency; the default cache is process-local. Production needs a shared cache and edge limits, including protection for requests rejected during authentication. These allowances are separate from staff API limits and the PostgreSQL-backed staff login limiter. Choose production rates and capacity from measured device traffic.

## Related event and update contracts

### Event batch ingestion

`POST /api/v1/device/events/` accepts UTF-8 `application/json` with exactly one envelope field, `events`. It must be an array containing 1–200 items by default (`DEVICE_EVENT_BATCH_MAX`). The complete request is limited to 2,097,152 bytes (`DEVICE_EVENT_BATCH_MAX_BYTES`), including whitespace. Invalid JSON, an invalid envelope or too many items returns HTTP 400; an oversized body returns 413 and a non-JSON content type returns 415. Envelope errors store no events. The body parser reads at most its byte limit plus one before decoding.

Each array item must be an object with these fields; unknown fields are rejected per item:

| Field | Contract |
| --- | --- |
| `event_id` | Required UUID string, stable across retries, scoped to the authenticated device. |
| `occurred_at` | Required ISO-8601 timestamp string with an explicit timezone offset or `Z`. Stored in UTC. Naive timestamps are rejected. |
| `code` | Required ASCII uppercase string matching `[A-Z0-9_]{1,100}`. |
| `state` | `info` (default), `active` or `resolved`, as reported by the device. |
| `fault_id` | Stable UUID string required for `active`/`resolved`; optional/null for `info`. A lifecycle update gets a new event ID and keeps this fault ID. |
| `summary` | Optional string, maximum 300 characters; defaults to empty. |
| `software_version` | Optional string, maximum 80 characters. Omitted/empty values use the device's recorded version on first acceptance. Retrying an omitted version keeps that original stored version even if the device has since checked in with a newer one. |
| `metadata` | Optional JSON object, default `{}`. Compact UTF-8 JSON size is limited to 16,384 bytes (`DEVICE_EVENT_METADATA_MAX_BYTES`). Root object counts as container level one; maximum nesting is eight dictionary/list levels (`DEVICE_EVENT_METADATA_MAX_DEPTH`). Null characters, invalid Unicode and non-finite numeric values are rejected. Never include passwords, credentials or signing secrets. |

Event time may be at most `DEVICE_EVENT_FUTURE_SKEW_SECONDS` (default 300 seconds) ahead of the server's batch receipt time. Older buffered events are retained without an additional historical-age cutoff. The server does not correct a device clock or infer fault transitions. It records the facts accepted under this contract.

Example request:

```json
{
  "events": [
    {
      "event_id": "00000000-0000-4000-8000-000000000001",
      "fault_id": "00000000-0000-4000-8000-000000000010",
      "occurred_at": "2026-11-15T10:00:00Z",
      "code": "FUEL_PRESSURE",
      "state": "active",
      "summary": "Device-reported pressure warning",
      "software_version": "2.4.1",
      "metadata": {"channel": 1}
    }
  ]
}
```

For a valid envelope, HTTP 200 returns a `results` array with the same length and order as the submitted array. Each result contains `event_id`, `status` and, when rejected, field-level `errors`:

```json
{
  "results": [
    {"event_id":"00000000-0000-4000-8000-000000000001","status":"accepted"}
  ]
}
```

- `accepted`: The immutable event, fault projection (when applicable) and communication freshness committed in one transaction.
- `duplicate`: The same normalized immutable facts already exist for this device/event ID. Metadata object key order and equivalent timezone representations do not create a different event. Receipt time and stored version remain unchanged.
- `rejected`: Validation failed or the ID already identifies different immutable facts. The original event and fault projection remain unchanged; a rejected item alone does not refresh connectivity. An invalid/non-string UUID is returned as `event_id:null`, and its position identifies the item. Arbitrary submitted IDs and raw metadata are not copied into rejection audit entries.

The device removes queue entries only after `accepted` or `duplicate`. Keep rejected entries for correction/operator review; never rewrite an already accepted event. A new reported fact needs a new event ID. Mixed batches may accept valid items while rejecting others, so inspect each result rather than treating HTTP 200 as whole-batch acceptance.

Each event commits independently. If a later storage/audit failure or credential revocation aborts the response, earlier events may already be stored even though no acknowledgement arrived. Retry every unacknowledged stable ID after resolving authentication/transport errors: committed items return `duplicate`, and uncommitted items can be accepted. The server serializes writes on the authenticated device and rechecks its current credential before each valid event write.

One server-assigned batch receipt time is retained on every newly accepted item. Occurrence time is independent and can precede receipt by a long offline interval. Freshness never moves backwards. Current fault state follows the greatest `(occurred_at, event_id)` pair, using UUID order for equal timestamps; late older events remain in history without overwriting newer reported state. The server does not diagnose or infer a transition.

Strict event fields, explicit timezone requirements and clock/metadata limits require device-owner compatibility review before production rollout. The actual durable queue client is not included in this repository.

The [backend README](../backend/README.md) documents event batch acknowledgement, UUID deduplication, delayed fault reports, update manifests and safe update-result states. Device software owns durable event queueing and retries. Keep production package rollout disabled until release authenticity is verified with the actual updater; SHA-256 package integrity alone does not authenticate a publisher.
