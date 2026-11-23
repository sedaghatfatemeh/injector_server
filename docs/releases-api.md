# Release and update-result contract

Staff routes use session authentication and CSRF protection for mutations. Support staff can read releases and assignments; only super administrators can publish, withdraw or assign rollback. Sensitive writes and their audit entries commit together. Package files remain on the external host.

`POST /api/v1/releases/` automatically publishes immutable metadata: `version`, `package_url`, `sha256`, `compatible_models`, optional `minimum_version` and `release_notes`, and exactly one target:

- `target_all_devices: true` with no selected devices (the default).
- `target_all_devices: false` with a nonempty `target_devices` array of device IDs.

Versions use the existing comparable `packaging.version.Version` format (an optional leading `v` is accepted). Digests must contain 64 hexadecimal characters and are normalized to lowercase. URLs must use HTTPS and must not include embedded credentials or fragments. Model names are trimmed and deduplicated; an empty list permits all models. Explicit selections must match the model rule and exclude archived devices/customers. Initial assignments include only devices whose reported current version meets the minimum and is older than the release. An unknown current version is eligible only when there is no minimum; an unparsable version is ineligible.

New devices can discover all-device releases; selected-device releases do not expand automatically. Manifest discovery rechecks the current model, version, target, archive status and assignment state. Withdrawn releases are retained but cannot be offered. `POST releases/{id}/withdraw/` withdraws a published release. Published metadata cannot be edited or deleted through the API.

`POST releases/{id}/rollback/` takes `device_ids` (1–1000 distinct positive IDs) and a nonblank `reason` (up to 1000 characters). All devices must be active, have active customer records, match the release model/minimum-version rules, and report a known version newer than the retained published release. Assignment and reason are audited atomically. Reassignment resets the assignment's current result and report timestamps; earlier audit records remain. Only explicitly selected devices receive downgrade permission. A withdrawn release must not be used as a rollback target.

## Device reports

`POST /api/v1/device/update-result/` uses the authenticated device credential, with no staff-session fallback. Fields:

```json
{
  "release_version": "2.0.0",
  "state": "downloaded",
  "result_code": "DIGEST_VERIFIED",
  "reported_at": "2026-11-16T10:00:00Z"
}
```

`result_code` is optional and blank by default; otherwise use up to 120 uppercase ASCII letters, digits or underscores. Send a diagnostic code, never free text, credentials, URLs, stack traces or raw payloads. Unknown fields are rejected. `reported_at` must have an explicit timezone and cannot exceed the event-clock tolerance (300 seconds by default) into the future. For older clients it is optional and falls back to server receipt time; clients must supply occurrence time for delayed-report protection.

| Current assignment state | Accepted next report |
| --- | --- |
| `available` | `downloading`, `downloaded`, `failed` |
| `downloading` | `downloaded`, `failed` |
| `downloaded` | `installing`, `failed` |
| `installing` | `succeeded`, `failed`, `rolled_back` |
| `succeeded`, `failed`, `rolled_back` | Identical retry only |

`available` is the server's assignment state, not a device result. Installation reports require the latest check-in to say `idle`. Devices retain final responsibility for safe installation; the API never starts or interrupts a test.

HTTP 200 returns `{"accepted": true}` after assignment and audit commit. Repeating the current state and result code returns `{"accepted": true, "duplicate": true}` without changing timestamps or adding an audit entry. A report older than the stored `reported_at` returns `{"accepted": true, "stale": true}` and is audited without regressing the projection. Conflicting codes for the same current state, distinct states sharing the latest timestamp, unknown assignments and invalid transitions return HTTP 400. Keep rejected reports for operator review. Send queued lifecycle reports in order; retry unacknowledged reports with their original timestamps and codes. This endpoint is a lifecycle protocol, not the UUID-based event-ingestion protocol.

Assignment reads expose `reported_at` (device occurrence time or legacy receipt fallback), `report_received_at` (server receipt time), and `updated_at` (projection modification time). A delayed success does not overwrite a software version from a newer check-in. Mutations lock the device and recheck its credential against concurrent rotation/revocation. Concurrent identical reports produce one state change and one audit entry.

Apply migration `0005_update_report_receipt` before starting the updated API. It preserves existing timestamps and copies legacy `reported_at` receipt times into `report_received_at`. Review the stricter diagnostic-code and timestamp contract with device owners before rollout.

## Production prerequisites and verification

With `DJANGO_DEBUG=false` and `DEVICE_UPDATE_ROLLOUT_ENABLED=false`, check-in advertises no update and manifests return `release_authenticity_not_verified`. Keep that gate disabled until signed metadata is implemented and verified end to end with the actual updater (REL-003). SHA-256 alone verifies integrity, not publisher authenticity. No signing protocol or key-custody decision is invented here.

Run the release, migration and existing API regression tests against the isolated PostgreSQL test database:

```powershell
docker compose -f compose.yaml -f backend/compose.test.yaml build api
docker compose -f compose.yaml -f backend/compose.test.yaml run --rm --no-deps api pytest devices/tests/test_releases.py devices/tests/test_api.py devices/tests/test_migrations.py
docker compose -f compose.yaml -f backend/compose.test.yaml run --rm --no-deps api python manage.py makemigrations --check --dry-run
```
