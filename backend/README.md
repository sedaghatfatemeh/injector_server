# Django API

The API uses Django, Django REST Framework, and PostgreSQL. It is a separate service from the Vite dashboard. The backend provides staff authentication, customer/device administration, device check-in, idempotent event ingestion, release metadata, update manifests, and update-result reporting. Python application packages are hosted externally; the API does not receive or serve package files.

## Local setup

Requires Python 3.11+ and PostgreSQL 15+.

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set the PostgreSQL environment variables from `.env.example` in the shell or your local environment. Django does not read `.env` automatically. Create an empty database and database user matching those settings, then:

```powershell
python manage.py migrate --run-syncdb
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

The Django superuser must have an email address because staff sign-in uses email and password. Use Django admin at `/admin/` to create a support user with `is_staff` enabled and `is_superuser` disabled. The API does not expose public account registration.

## Main routes

All routes are versioned under `/api/v1/`.

| Route | Auth | Purpose |
|---|---|---|
| `POST auth/login/` | Public, throttled | Exchange staff email/password for a staff API token |
| `POST auth/logout/` | Staff | Revoke the current staff token |
| `GET dashboard/summary/` | Staff | Fleet counts and data freshness |
| `customers/` | Staff; super admin writes | Search and manage customer records |
| `devices/` | Staff; super admin writes | Search and manage the fleet |
| `devices/{id}/events/` | Staff | Paginated device event history |
| `events/` | Staff | Search/filter paginated events |
| `releases/` | Staff read; super admin writes | Add/list Python app release metadata; creation publishes automatically |
| `releases/{id}/assignments/` | Staff | Inspect per-device rollout status |
| `releases/{id}/rollback/` | Super admin | Reassign a retained older release to selected devices with an audited reason |
| `device/check-in/` | Device token | Update version, safe/idle state, and last contact |
| `device/events/` | Device token | Submit up to 200 events idempotently |
| `device/update-manifest/` | Device token | Get an eligible update manifest |
| `device/update-result/` | Device token | Report installation outcome |

Staff calls use `Authorization: Token <staff-token>`. Device calls use `Authorization: Device <device-token>`. Device credentials are stored as SHA-256 digests and are shown only once during provisioning/rotation:

```powershell
python manage.py provision_device PZ-2024-0186
```

Event payloads include a stable `event_id` UUID, an ISO-8601 `occurred_at` timestamp, a stable uppercase `code`, reported state, and optional structured metadata. Device software should durably queue events and retain them until each event is acknowledged as `accepted` or `duplicate`. A repeated ID with a different code or occurrence time is rejected.

Fault lifecycle messages use a distinct stable `fault_id` as well as a new `event_id` for each update. For example, report an `active` event with fault ID `F` and later a new `resolved` event with the same fault ID `F`. This preserves immutable event history while allowing the API to show the current reported fault state. Delayed, out-of-order events are retained, but an older occurrence time does not replace a newer current fault state.

Create a release with its version, externally hosted HTTPS `package_url`, 64-character SHA-256 digest, compatible model names, and release notes. Also set exactly one target: `target_all_devices: true` or a non-empty `target_devices` array of registered device IDs. The record is published automatically to that compatible target. Devices retrieve the manifest and download directly from the external URL.

## Important implementation boundary

The device remains responsible for local durable queueing, retry/backoff, fault diagnosis, and deciding when it is safe to install. The API never sends real-time test-control commands. The API stores the expected SHA-256 digest but does not yet verify publisher signatures. A production signing-key/public-key verification workflow must be selected and implemented before remote update delivery is production-ready. Production deployment, backup/retention, external hosting policy, and API validation also remain to be configured.
