# Pishgaman Shargh Injector Management MVP

This repository contains the Persian RTL dashboard prototype and a Django/PostgreSQL API scaffold for the MVP. The dashboard still uses sample data. The backend implements authenticated staff APIs, customer/device records, device check-in, idempotent event ingestion, update metadata, and rollout status.

## Run the backend locally with Docker

1. Copy `.env.example` to `.env` and replace the development secret and database password.
2. Start PostgreSQL and Django:

   ```powershell
   docker compose up --build
   ```

3. In another terminal, create the initial superuser:

   ```powershell
   docker compose exec api python manage.py createsuperuser
   ```

4. Open Django admin at `http://localhost:8000/admin/`. The superuser email is used to sign in to the API. Create support users there with `is_staff` enabled and `is_superuser` disabled.

The API is available at `http://localhost:8000/api/v1/`. See [`backend/README.md`](backend/README.md) for endpoint details and device payload examples.

## Run the dashboard prototype

The front end is separate and still uses local sample data:

```powershell
npm.cmd install
npm.cmd run dev
```

The frontend has not yet been wired to the API, by decision. Follow [`product_spec.md`](product_spec.md) for the product scope and [`design-spec.md`](design-spec.md) for the visual system.

## Interactive onboarding prototype

The standalone, backend-free walkthrough is in [`sites/injector-onboarding/index.html`](sites/injector-onboarding/index.html). It simulates staff sign-in, customer and device registration, a device connection/offline sync flow, event review, and a safe software update. Demo state is kept only in browser `localStorage`. The generated static package is in `sites/injector-onboarding/dist/`.

## Current boundary

The server does not control a test. Each device must durably queue its own events and decide when installation is safe. Software packages are hosted externally; the API stores the version, HTTPS URL, compatibility, and expected SHA-256 digest, then publishes a release automatically when an authorized super administrator creates it. Release-signature verification, device client integration, production hosting, backups/retention, and API validation remain before production use.
