# Customer and device inventory contract

Internal support staff can read, search and paginate inventory. Active staff super administrators can create, edit and archive it. Browser mutations require a staff session and CSRF; device credentials never authorize these operations. The [role matrix](staff-permissions.md) describes permission and denial auditing.

## Customer records

`/api/v1/customers/` and `/api/v1/customers/{id}/` support registration, detail and administrative updates. Organization name and contact name are required nonblank strings. At least one email or phone contact method must remain present, including after partial or concurrent edits. Address and notes remain optional under the current product minimum.

Names are trimmed and email is trimmed/lowercased. Phone inputs normalize Persian/Arabic digits to ASCII and remove common whitespace, parentheses, dots and hyphens while retaining the country-code `+` and other text. No country code or region is inferred. Existing records are not bulk-rewritten; phone search also normalizes historical formatted values in the query. `device_count` counts non-archived associated devices and is server-derived.

`search` supports organization/contact/email/phone, with normal multi-term search and numeric phone normalization. `ordering` supports organization name and creation time; a primary-key tie-break keeps pagination deterministic. `is_archived=false` is the default; `is_archived=true` selects archived profiles. Boolean flags must be the literal `true` or `false`; malformed/empty flags return HTTP 400.

## Device records and current reported facts

`/api/v1/devices/` and `/api/v1/devices/{id}/` register and manage serial number, model, customer and site metadata. Serial numbers are trimmed, case-sensitive and globally unique across active and archived records. A duplicate creates a field-level `serial_number` error with HTTP 400, including concurrent registrations/edits. Unrelated storage/audit failures remain retryable server errors and are not reported as serial conflicts.

New registrations and reassignment require an active customer. An existing device may keep its current archived customer while administrative metadata is edited. Restoring an archived device requires an active customer, which can be supplied in the same update. Responses expose `customer_is_archived` so the current relationship is explicit.

Initial `software_version` can be entered/edited before the device has communicated. Once `last_seen_at` is populated, software version is controlled by device check-in and update-result reports and is read-only in the inventory edit form/API. `install_state`, `last_seen_at`, online estimate and active fault count are always server-derived/read-only here. A check-in that arrives during an administrative edit is preserved: writes reload and lock the current device before applying metadata. Partial edits of different fields do not save an obsolete copy of the whole record.

Creation, editing and archiving commit with their audit entries. Device update audits retain before/after snapshots, including the old and new customer IDs, and a `customer_changed` flag. Only known inventory fields are copied into these snapshots. Customer contact-method validation is repeated under its row lock so concurrent removals cannot leave a customer with no contact method.

## Search, filters and pages

Device search covers serial, model and customer organization. Filters combine `customer` (ID), `model_name`, `online=true|false`, `has_active_faults=true|false` and `is_archived=true|false`. Inventory defaults to non-archived devices, ordered by serial and primary key. A requested ordering receives a deterministic primary-key tie-break. Online state is an estimate from the configured communication threshold; it does not establish device safety.

All lists return `count`, `next`, `previous` and `results`, with 50 rows per page by default. Preserve filters/order when following `page=2` or later pages.

`GET /api/v1/customers/{id}/devices/` returns a paginated inventory scoped only to that customer. It excludes archived devices by default; `include_archived_devices=true` includes both active and archived children. For an archived customer, also pass `is_archived=true` to select the parent profile.

## Archive and retained history

DELETE archives records rather than physically deleting them. Customer profile archiving is independent of device archiving: it hides the customer from the default customer list, but does not archive associated devices, revoke their credentials or interrupt their work. Existing devices remain visible in inventory with `customer_is_archived:true`; their authenticated communications continue. New assignment to that archived profile is rejected.

Device archiving excludes it from the default device list and rejects subsequent device authentication while archived. Events, update assignments, serial uniqueness and ownership references remain stored. Restoring a device does not rotate its credential; revoke/rotate explicitly when credential lifecycle changes are required.

Examples for authorized staff:

```text
GET /api/v1/devices/{id}/?is_archived=true
GET /api/v1/devices/{id}/events/?is_archived=true
GET /api/v1/devices/{id}/updates/?is_archived=true
GET /api/v1/customers/{id}/devices/?is_archived=true&include_archived_devices=true
```

Device history hides an archived customer by default. Add `device__customer__is_archived=true` to the device event/update history request to include it. For example, history where both device and customer are archived uses `?is_archived=true&device__customer__is_archived=true`. The global event list retains its documented `device__is_archived=true` and `device__customer__is_archived=true` opt-in flags. Records remain attached to the same device ID after an audited reassignment; this is an internal staff API, not a customer portal.

## Verification

`backend/devices/tests/test_inventory.py` covers normalization/search, minimum contacts, assignment boundaries, initial and reported software versions, stale-edit preservation, audit rollback, archive/history access, scoped pagination and concurrent contact/serial edits against PostgreSQL. Use the Pytest command in the [backend README](../backend/README.md). Browser acceptance additionally exercises real customer/device forms against an isolated database; QA records are removed with that database.
## Device model catalog (approved 2026-11-24)

`GET /api/v1/device-models/` lists the paginated catalog for authenticated staff;
supports `search`, `kind`, `edition` and `is_active` filters. Customers and device
bearer credentials cannot access this endpoint. Only super administrators may
POST a model or PATCH/PUT its detail endpoint. Deletion is unsupported.

Fields: `id`, `code` (unique, normalized uppercase, at most 120 characters),
`display_name`, `kind` (`unit`, `cr`, `combo`, `pump`, `pro`), `edition` (`b`, `pc`,
`e`), `is_active`, and read-only labels/timestamps. Code, kind and edition are
immutable after creation; display name and active status can be edited with audit
records. Inactive models remain visible for existing device records but cannot
be newly assigned. The device/model link uses a protected foreign key.

New device registrations must include `device_model` (catalog ID) and `customer`;
free-text `model_name` alone is no longer sufficient. A matching `model_name` may
be supplied, but conflicting values are rejected. Responses keep `model_name` as
the compatibility code and add `device_model` and `model_display_name` for staff.
Each customer can own multiple devices; serial uniqueness remains global.

Run migrations 0007 and 0008 before deploying this frontend/API pair. They seed
the 15 reference codes (`AD-{UNIT,CR,COMBO,PUMP,PRO}-{B,PC,E}`). Existing device
strings that exactly match these codes are linked; unmatched legacy strings stay
unchanged with a null catalog ID. Editing other fields on those devices does not
require inventing a mapping. Changing their model requires selecting a catalog ID.

Release compatibility remains keyed by the existing `model_name` string. Migration
does not rewrite release metadata, assignments or legacy names. Renaming a catalog
display label has no effect on compatibility; changing a device's selected model
intentionally changes its compatibility key and is audited. Customer responses
retain their existing safe allowlist; this does not expose the staff catalog.
