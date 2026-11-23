# Django API

The backend is a Django REST Framework service backed by PostgreSQL. Staff and customers use expiring, HttpOnly session cookies with CSRF protection and separate server-enforced roles. Devices use separate revocable bearer credentials; the database stores only their SHA-256 digests. The API stores update metadata only: Python packages remain on an external HTTPS host.

## Local setup

Use Python 3.12 and PostgreSQL 17. Copy `.env.example` to `.env`, set the database credentials, and export those variables in the shell (Django does not load `.env` automatically). The Compose setup at the repository root provides PostgreSQL and the API container.

```powershell
Copy-Item .env.example .env
docker compose up -d db
docker compose build api
docker compose run --rm api python manage.py migrate
docker compose up -d api
docker compose exec api python manage.py createsuperuser
```

Run the dashboard separately with `npm.cmd install` and `npm.cmd run dev`; API requests use same-origin `/api/v1/` paths by default. To explicitly view the sample-data prototype, set `VITE_DEMO_MODE=true`; production defaults to live data and never falls back to sample records. Create the first super administrator with `createsuperuser`, then sign into the console and open **کاربران** to add staff accounts. Choose support (the default, read-only operational access) or super administrator (full staff and operational administration). The server validates passwords, hashes them, rejects existing email addresses case-insensitively, and audits account creation without storing the password in the audit record. Deliver the initial password through a secure channel. Only super administrators may list or create staff accounts through the API. Existing Django admin provisioning remains available: set `is_staff`, leave `is_superuser` false for support, and add support users to the `support` group. Ensure emails are unique when provisioning through Django admin; ambiguous duplicate emails cannot sign in. Staff sign in using their email address.

### Connect desktop pgAdmin to the local database

The base Compose file keeps PostgreSQL private to Docker. For desktop pgAdmin or native Python development, enable the optional loopback-only port from the repository root:

```powershell
docker compose -f compose.yaml -f compose.pgadmin.yaml up -d db
```

In pgAdmin, register a server with host `127.0.0.1`, port `5432`, maintenance database equal to `POSTGRES_DB` in the root `.env` (default `injector_server`), username equal to `POSTGRES_USER` (default `injector_server`), and password equal to `POSTGRES_PASSWORD`. Use `127.0.0.1` for desktop clients; `db` is the hostname used between Compose containers. For native Django development, export `POSTGRES_HOST=127.0.0.1` in that shell.

The pgAdmin account/master password and the staff console password are separate from the PostgreSQL role password. Changing `.env` alone does not reset passwords in an already initialized PostgreSQL volume. This override retains the existing database volume and publishes the port only on this computer; keep it out of production startup commands. If another PostgreSQL service already uses port 5432, select another free host port in the override and use that port in pgAdmin.

### Locked Python development environment

The backend targets Python 3.12 and Django 5.2 LTS. Install `uv` 0.13.6, then run from `backend/`:

```powershell
uv sync --locked
uv lock --check
```

`uv` creates `.venv` and uses `.python-version` to select Python 3.12 (downloading it if needed). `pyproject.toml` is the dependency source of truth and `uv.lock` fixes the resolved versions. Development tools are in the `dev` dependency group; `uv sync --locked --no-dev` installs runtime dependencies only. Gunicorn is installed on Unix/container environments, not Windows. To change a dependency deliberately, edit `pyproject.toml`, run `uv lock`, and review both files together. Do not recreate a separate `requirements.txt`.

Export the database and Django environment variables in the shell (`.env` is not loaded automatically), and ensure PostgreSQL is reachable before running:

```powershell
uv run --locked python manage.py check
uv run --locked python manage.py migrate
uv run --locked python manage.py runserver 127.0.0.1:8000
uv run --locked pytest
uv run --locked ruff check .
```

Tests create a separate PostgreSQL test database; the configured local test role must be allowed to create databases. Do not point tests at production. The Compose database is private to its network; use the development image to run checks/tests against it without exposing a database port. Run these commands from the repository root:

```powershell
docker compose up -d db
docker compose -f compose.yaml -f backend/compose.test.yaml build api
docker compose -f compose.yaml -f backend/compose.test.yaml run --rm --no-deps api pytest
docker compose -f compose.yaml -f backend/compose.test.yaml run --rm --no-deps api python manage.py check
docker compose -f compose.yaml -f backend/compose.test.yaml run --rm --no-deps api python manage.py makemigrations --check --dry-run
```

`backend/compose.test.yaml` selects the local `injector-api-dev` image and does not change the running API service. The production Docker target installs only locked runtime dependencies; test/lint tools are available in the development target.

The PostgreSQL suite covers device credential rotation/revocation, role and CSRF boundaries, administrator staff provisioning, globally unique device serials (including archived inventory), per-device event identity, duplicate/conflicting delivery, delayed/concurrent faults, release targeting and safe update outcomes. `devices/tests/test_migrations.py` also installs the product schema from empty and rehearses `0001_initial` → `0002_domain_metadata` with existing operational records. It changes only the isolated test database and restores the current schema before returning. Use the same Pytest command with `devices/tests/test_migrations.py` to run just that migration check.

`uv run --locked python manage.py makemigrations --check --dry-run` verifies that model changes have migrations. Do not use `--run-syncdb` for the product schema. For an existing database created with syncdb, take and verify a backup, inspect that the existing tables and constraints match the pre-metadata schema in `0001_initial`, and only then run `python manage.py migrate devices --fake-initial` once. Django will then apply `0002_domain_metadata` to add customer address/notes and update report timestamps. An empty database uses ordinary `migrate`.

## Routes

The [inventory contract](../docs/inventory-api.md) defines customer/device fields, normalization, reassignment audits, reported facts, archive/history flags and deterministic pagination.

### Staff session and login policy

Staff sign-in uses email/password and a rotated, HttpOnly, SameSite session cookie. `STAFF_SESSION_AGE_SECONDS` defaults to 28,800 seconds (eight hours); read-only requests do not extend that lifetime. Logout deletes the server session. Expired sessions, inactive accounts and sessions invalidated by password changes cannot access staff APIs. Production (`DJANGO_DEBUG=false`) enables Secure session/CSRF cookies and HTTPS redirects; finalize the trusted HTTPS origin and proxy configuration before deployment.

`STAFF_LOGIN_RATE` defaults to `10/minute`. It applies per client address to all login requests, including requests from signed-in staff. A fixed time window is stored and locked in PostgreSQL, so separate Gunicorn workers share one limit and concurrent requests cannot each spend the same remaining attempt. Throttled requests return HTTP 429 with `Retry-After`. Counter keys are keyed digests; raw client addresses, emails and passwords are not stored in these counters. Successful sign-ins/sign-outs and denied/throttled sign-ins create audit entries without submitted credentials. A successful login requires its audit write to succeed.

The [staff permission matrix](../docs/staff-permissions.md) defines operational reads, super-administrator-only writes, denied-action audits and native admin access. Removing `is_staff` also removes superuser console access. Django admin accepts only active staff super administrators, shares the console's login limiter, audits native sign-in/account changes, and keeps operational events and audit records read-only.

`API_NUM_PROXIES=0` ignores `X-Forwarded-For` by default. Set a positive count only after configuring the actual trusted reverse-proxy chain to replace untrusted forwarding headers. When a proxy is present and this remains zero, clients behind that proxy share its address-based limit. This shared login limiter does not replace perimeter protection or the separately configured general API throttles.

Apply migration `0003_staff_login_throttle` with the normal one-off `migrate` step before starting the updated API. Schedule the following maintenance command daily in the eventual hosting environment; it removes counters older than seven days and preserves active rate-limit windows:

```powershell
docker compose exec api python manage.py prune_login_throttles
```

All application API routes are versioned under `/api/v1/`.

| Route | Access | Purpose |
|---|---|---|
| `POST auth/login/` | Public, throttled, CSRF-protected | Create a staff or eligible customer session from email/password |
| `GET auth/session/`, `GET auth/csrf/` | Eligible browser session / public | Restore current role/organization and bootstrap CSRF |
| `POST auth/logout/` | Browser session + CSRF | End the server session |
| `GET staff-users/`, `POST staff-users/` | Super-administrator session; CSRF for POST | Paginated/searchable staff directory and audited account creation |
| `GET customer-users/`, `POST customer-users/` | Super-administrator session; CSRF for POST | Paginated/searchable customer-account directory and audited creation with organization assignment |
| `PATCH customer-users/{id}/` | Super administrator + CSRF | Change only `is_active`; roles, credentials and organization cannot be reassigned here |
| `GET customer/devices/`, `GET customer/devices/{id}/` | Eligible customer session | Paginated own-organization active devices and allowlisted read-only details |
| `GET customer/summary/` | Eligible customer session | Own-organization device/online/offline counts and freshness basis |
| `GET dashboard/summary/` | Staff | Fleet metrics and freshness time |
| `customers/`, `devices/` | Staff read; super-admin write | Search and manage inventory |
| `GET customers/{id}/devices/` | Staff | Paginated devices scoped to the selected customer |
| `POST devices/{id}/provision_credential/` | Super admin | Rotate credential, return the secret once |
| `POST devices/{id}/revoke_credential/` | Super admin | Revoke the credential without issuing a replacement |
| `devices/{id}/events/`, `events/` | Staff | Paginated device history and event search |
| `releases/`, `releases/assignments/` | Staff read; super-admin publish/withdraw/rollback | Release registry and device outcomes |
| `POST device/check-in/` | Device credential | Report version, idle/testing state and check-in |
| `POST device/events/` | Device credential | Submit up to 200 idempotent events per batch |
| `GET device/update-manifest/` | Device credential | Discover a compatible assigned release |
| `POST device/update-result/` | Device credential | Report update lifecycle result |
| `GET /health/live/`, `/health/ready/` | Public | Process liveness and database readiness |

For direct device provisioning, `python manage.py provision_device <serial>` prints a new secret once. Send it as `Authorization: Device <secret>`. `python manage.py revoke_device_credential <serial>` revokes it without printing a replacement. Both operations commit with their audit entry or roll back together. Never put the raw credential into tickets or logs. The [device API contract](../docs/device-api.md) describes check-in fields, errors, body limits, per-endpoint rates, credential handling, and device-client rollout prerequisites.

Event payloads contain a stable UUID `event_id`, explicitly timezone-qualified ISO-8601 `occurred_at`, uppercase `code`, reported state, optional stable `fault_id`, and an object of metadata up to 16 KiB and eight container levels. The default batch limit is 200 events / 2 MiB; future event times may be at most five minutes ahead of server receipt time. All limits are configurable. Repeated identical events are acknowledged as duplicates; reuse of an ID with different facts is rejected and audited. Events are immutable. Fault updates create new events; the newest occurrence time (UUID order breaks ties) drives the reported current state. One server receipt time is retained for newly accepted events in the batch. Each event, its fault projection and monotonic last-seen update commit together. An invalid-only batch does not update last-seen. If a later event fails, earlier commits remain; retry the unacknowledged batch with the same event IDs. See the [event batch contract](../docs/device-api.md#event-batch-ingestion) for per-event results, validation and queue rules.

Apply migration `0004_event_receipt_time` before starting this API version. It preserves existing receipt timestamps while allowing the ingestion service to assign a single server receipt time explicitly.

Create releases with a version, external HTTPS `package_url`, 64-character SHA-256 digest, compatible model names, release notes, and exactly one target (`target_all_devices: true` or a non-empty `target_devices` array). Publication creates assignments for compatible active target devices. Device software decides whether it is safe to install. SHA-256 checks package integrity but does not authenticate the publisher; production device rollout remains blocked until signed metadata is supported and verified end to end with the actual updater.

The [release API contract](../docs/releases-api.md) specifies version eligibility, retained-release rollback, canonical lifecycle states, retry behavior, sanitized result codes, and delayed reports. Apply `0005_update_report_receipt` with the one-off migration command before starting this API version. Device results may include timezone-qualified `reported_at`; assignment reads expose it separately from server `report_received_at`. Confirm the stricter result-code schema with device owners before rollout.

### Event history filters

`GET /api/v1/events/` returns `count`, `next`, `previous`, and up to 50 `results`; use `page=2` for subsequent pages. Default ordering is newest occurrence first, with descending ID breaking timestamp ties. Filters can be combined: `search`, `state`, `device`, `device__customer`, `code`, `device__serial_number__icontains`, and `device__customer__organization_name__icontains`. `occurred_after` and `occurred_before` are inclusive ISO-8601 timestamps with an explicit timezone. Invalid dates or reversed ranges return HTTP 400. Archived inventory remains hidden by default.

The console's event history supports search, device serial, customer name, state, and occurrence date range, with previous/next navigation and retry. Dates entered in the browser's local timezone are converted to UTC for API requests.

## Security and deployment

### Customer membership and upgrade

Apply `0006_customer_membership` with the normal one-off migration command before starting the updated backend. It adds a separate table linking the existing Django user model to Customer, with a unique user relation and a protected organization foreign key. It does not modify or automatically associate existing accounts. Customer contact emails are contact data, not login identities. Multiple customer accounts can belong to one organization; each account has exactly one membership. Customer identities with staff/superuser flags or the support group fail closed, including on staff APIs and native admin. Native staff-user forms exclude customer accounts; use the audited customer-account interface to manage them.

For a local existing checkout, preserve a database backup before upgrading and use:

```powershell
docker compose build api
docker compose run --rm api python manage.py migrate
docker compose up -d api
```

The PostgreSQL migration test rehearses an empty install and preservation of existing users, devices, events, assignments, audits and timestamps through the current schema, with zero inferred customer memberships. Rehearse an upgrade on a disposable copy before a production release. Rolling back this schema removes membership links; prefer a forward fix or a rehearsed backup restoration rather than blindly reversing migrations. Existing staff records and passwords remain unchanged.

Super administrators create customers through **حساب‌های مشتریان**, supplying email, validated initial password, optional names and the active organization's ID. Creation, membership and audit commit atomically. Only `is_active` can be patched afterward; no public registration, invitation email or customer credential/role editing is provided. Deactivation blocks an existing session on its next protected request. Reactivation of an archived organization's account is denied. The existing `STAFF_SESSION_AGE_SECONDS` and `STAFF_LOGIN_RATE` settings now apply to both browser roles, preserving configuration compatibility; safe cookie/CSRF and proxy rules remain the same.

Customer APIs resolve organization from current membership on each request. Missing membership, inactive account, archived organization or a mixed staff/customer identity denies access. Device reassignment removes the former organization's visibility on subsequent requests; archived devices are excluded. Organization archival still does not interrupt devices or revoke device credentials.

Device list parameters are `search` (serial/model, at most 200 characters), `online=true|false` and `page`; unknown or repeated parameters are rejected. Response device fields are only `id`, `serial_number`, `model_name`, `software_version`, `location`, `last_seen_at`, and `is_online`. Foreign and missing detail IDs both return 404. Summary returns only organization device/online/offline counts, `generated_at` and `online_window_minutes`. No credentials, contacts, internal notes, events/faults, releases or audit data are exposed. Browser identity and customer-data responses use no-store caching rules.

The customer UI revalidates on refresh, browser focus/visibility and every 60 seconds while visible, clearing pending/stale records when identity or access changes. This is periodic monitoring, not a live connection. It displays the configurable threshold and never-connected state; it cannot connect to or control a device. For static production hosting, route `/customer/devices` and `/customer/devices/:id` to the SPA entry document; preserve `/api/` routing to Django. Vite provides this fallback locally.

### Production configuration

Gunicorn serves collected Django admin CSS/JavaScript through WhiteNoise middleware. The production image runs `collectstatic` at build time using compressed, hashed static assets; no separate static server is required for the admin. After changing backend dependencies or static configuration, rebuild the API image, apply pending migrations, and recreate the local API container. `/static/admin/css/base.css` must return HTTP 200 with a CSS content type. Missing styles on `/admin/` indicate a static delivery problem, not an account or database-password problem.

Set a private `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, explicit `DJANGO_ALLOWED_HOSTS`, HTTPS, trusted origins, and Secure cookie settings in production. Keep `DEVICE_UPDATE_ROLLOUT_ENABLED=false` until signed release metadata is verified end to end with the actual device updater; SHA-256 alone is not publisher authentication. Never expose PostgreSQL publicly. The Docker image runs non-root under Gunicorn. Apply migrations as a one-off task before starting/updating API replicas; the API entrypoint does not mutate schema. Configure provider-managed backups, retention, restore exercises, logging/alerts, and SLO/RPO/RTO before production; provider and operational targets remain open product decisions.

The API never controls a running test, interrupts device work, diagnoses faults, or installs an update. Local event queueing and safe-point update installation remain device responsibilities.
