# Pishgaman Shargh Injector Management MVP

This repository contains Persian RTL staff and customer panels, a Django REST API, and a separate onboarding walkthrough. The console uses live API data by default; set `VITE_DEMO_MODE=true` to explicitly view the sample-data prototype.

## Start the backend locally

For a step-by-step Windows walkthrough in Persian, see [راهنمای اجرای محلی پروژه](docs/local-setup.fa.md).

For the complete setup, staff/customer journeys, device and update contracts, acceptance checks, and verification limits, see [راهنمای جامع گام‌به‌گام](docs/walkthrough.fa.md).

For the separate second edition with real panel screenshots, see [نسخه ۲ راهنمای تصویری](docs/walkthrough.v2.fa.md). The original guide remains unchanged.

1. Copy `.env.example` to `.env` and set a private development secret and database password.
2. Build the API and start PostgreSQL:

   ```powershell
   docker compose build api
   docker compose up -d db
   ```

3. Apply migrations once, then start the API:

   ```powershell
   docker compose run --rm api python manage.py migrate
   docker compose up -d api
   ```

4. Create the first super administrator and open Django admin at `http://localhost:8000/admin/`:

   ```powershell
   docker compose exec api python manage.py createsuperuser
   ```

After creating the first super administrator, sign into the console and open **کاربران** to add support or super-administrator staff accounts. Support accounts are placed in the `support` group automatically and cannot access user management. The console signs staff in with expiring, CSRF-protected session cookies. API and device setup details are in [`backend/README.md`](backend/README.md).

To provision a customer, register the customer organization and its devices, then open **حساب‌های مشتریان** as a super administrator. Create an account and select its active organization. Deliver its initial password through a secure channel. The shared login sends customers to `/customer/devices`, where they can view only their organization's assigned device details and estimated connectivity. Multiple accounts can share one organization; each account belongs to one organization. Customers cannot register themselves, manage devices or staff, read operational event/release/audit records, or control tests. Deactivating the account blocks existing sessions on their next request. See the [Persian customer setup instructions](docs/local-setup.fa.md#ورود-مشتری-و-پنل-اختصاصی).

Existing checkouts must rebuild the API and apply additive migration `0006_customer_membership` before using the updated backend. It does not convert existing staff or infer customer membership from contact emails. Preserve and back up existing databases; do not remove volumes or rewrite applied migrations.

Backend dependencies are declared in `backend/pyproject.toml` and locked in `backend/uv.lock`, targeting Python 3.12 and Django 5.2 LTS. For native development, run `uv sync --locked` from `backend/`. The Docker production target installs runtime dependencies only; the development target includes Pytest and Ruff. See the [backend development and PostgreSQL test commands](backend/README.md#locked-python-development-environment).

## Start the dashboard

```powershell
npm.cmd install
npm.cmd run dev
```

The API client uses same-origin `/api/v1/` by default. For local Vite development, configure an API base URL or the allowed CORS/CSRF origins. Sample records appear only when the explicit `VITE_DEMO_MODE=true` flag is set.

## Task tracking

This project uses Beads for implementation tasks and dependencies. Run
`./scripts/bd.cmd ready` to see available work. See
[`docs/development-workflow.md`](docs/development-workflow.md) for installation,
daily commands, and the policy for issue snapshots and database backups.

## Interactive onboarding prototype

The approved interface reference in [`prototype/onboarding/index.html`](prototype/onboarding/index.html) keeps demo state in browser `localStorage` and does not connect to the live API.

## Production prerequisites

The server never controls a test. Device software owns durable event queueing and decides when installation is safe. Packages remain on an external HTTPS host. SHA-256 verifies package integrity but does not authenticate the publisher: production device rollout requires signed release metadata verified against the actual updater. Hosting provider, backup/retention policy, and operational targets also remain to be selected.
