# Frontend verification

The live console follows the Persian RTL onboarding reference in `prototype/onboarding/`. Demo records remain behind the explicit `VITE_DEMO_MODE=true` switch. Browser tests below use mocked API responses and do not provision staff, log into real accounts, or modify the local database. PostgreSQL API tests separately verify authentication, CSRF, roles and domain behavior.

Install the locked frontend dependencies and build the application from the repository root:

```powershell
npm.cmd ci
npm.cmd run build
npm.cmd run test:browser
```

Browser tests use the installed Microsoft Edge on Windows and Playwright Chromium on other platforms. To use Chrome on Windows, set `$env:PLAYWRIGHT_CHANNEL='chrome'` before running them. On Linux/CI, install the browser once with `npx playwright install --with-deps chromium`. To select installed Edge explicitly, set `PLAYWRIGHT_CHANNEL=msedge`. The test configuration uses a separate Vite instance on `127.0.0.1:5174`, leaving the normal development console on port 5173 available. Outside CI it can reuse an existing Vite instance on that test port; do not run a demo-mode instance there.

The shell checks cover pending session restoration, role-based navigation, customer and staff dialogs, Tab/Shift+Tab containment, Escape dismissal, focus restoration, mobile drawer navigation, RTL layout, theme persistence, disabled browser storage, invalid gateway responses and session expiry during event review. Dialogs use the native modal layer, making the background inert, with a shared keyboard/focus boundary. Header close controls and Escape respect the form's saving state. Shared shell text lives in `src/locale.js`; feature copy can move to the same boundary as further screens are extracted.

The API client rejects successful non-JSON gateway pages rather than treating them as empty data. Loading requests carry a revision check so an older response cannot overwrite newer search/navigation results or restore cleared data after logout. A failed refresh displays an error while the previous summary retains its original freshness timestamp.

Customer-panel tests in `tests/browser/customer.spec.js` additionally cover role dispatch without staff API calls, direct device routes and refresh/back navigation, never-connected status and configured threshold, foreign/reassigned detail cleanup, mobile RTL drawer/focus/theme, API outage versus empty fleet, logout/expiry, changed organization, and administrator customer-account creation/deactivation. The shared sign-in heading is **ورود به سامانه** for both browser roles. Customer refreshes clear old records while loading and abort/invalidate pending responses; data is revalidated on focus, visibility and every 60 visible seconds.

For a real-backend walkthrough, start Docker/PostgreSQL and Vite as described in [the local setup guide](local-setup.fa.md), sign in with a provisioned staff account, and inspect customer/device workflows, expired sessions and permission errors. Browser mock tests do not replace that walkthrough or the PostgreSQL security suite. The suite's session fixture collects admin static assets into a temporary directory, using the production manifest storage without changing checkout files.

## Reproducible real-backend customer acceptance

From the repository root, with the local Compose database running and locked frontend dependencies installed:

```powershell
docker compose -f compose.yaml -f backend/compose.test.yaml build api
node scripts/customer-browser-qa.mjs
```

The script creates a uniquely named disposable PostgreSQL database, applies migrations from empty, and seeds temporary staff/organization/device fixtures. It mounts backend source read-only into a temporary development-image API on loopback port 8006 and starts a separate Vite process on 5186. The API origin is explicitly pinned to that proxy; it never uses the running application for QA logins. Random initial passwords are passed via process stdin, never printed or persisted. Only generated test data is used. The test does not deploy, migrate the ordinary application database or restart its services.

Nine real Edge checks passed: administrator account creation, invalid/valid customer login and never-connected state, HttpOnly cookie/safe response/tenant and staff denial, refreshed direct detail routes, account deactivation/reactivation, mobile RTL/drawer/dark theme, device reassignment cleanup, actual server-session expiry/logout revocation, and existing support login/provisioning denial. Screenshots and a secret-free results file are under ignored `.local/customer-scope/artifacts/`.

Cleanup removes only the randomly named QA container with its matching database label, then drops that generated database. The development DB role must have create/drop database permission. If cleanup fails, the script reports the QA database name and exits unsuccessfully; investigate that named QA resource rather than deleting the ordinary database volume. Ports 8006 and 5186 must be free. Production TLS/cookie/proxy and static SPA fallback still need provider-specific validation.

Verification checkpoint (2026-11-18): the complete PostgreSQL suite passed **278 tests**, the combined mocked browser suite passed **15 tests**, and the isolated real-backend Edge walkthrough passed **9 checks**. `npm.cmd run build`, backend `ruff check --no-cache .`, Django `check`, `makemigrations --check --dry-run` and `git diff --check` passed. New API tests clear their in-memory DRF throttle cache between cases; the production PostgreSQL login limiter remains unchanged. QA databases and API/Vite processes created by the real-backend script were removed afterward.
## Persian calendar and Tehran time (injector-cz3)

All live date/time displays share `src/dates.js` through `EventTable.formatDate`.
The calendar is explicitly Persian and the timezone is `Asia/Tehran`, independent
of the browser's timezone. Missing or invalid timestamps show a dash. Historical
prototype/sample-data copy remains separate from the live interface.

Event occurrence range inputs accept Persian, Arabic or ASCII digits in
`YYYY/MM/DD HH:mm:ss` form (seconds and the time are optional; a date alone means
00:00:00 Tehran). The month grid supports month/year selection, arrow keys,
Home/End, PageUp/PageDown, Enter, Escape, and direct text entry. Input dates and
times are validated rather than silently constrained, including leap-year dates.
Historical Tehran DST gaps and ambiguous repeated times are rejected explicitly.

`@internationalized/date` supplies calendar arithmetic. Convert to the Gregorian
calendar before strict timezone conversion; do not parse Persian text with native
`new Date()`. API parameters stay ISO-8601 UTC. Empty bounds are omitted, equal
bounds are allowed, reversed bounds are rejected, and occurrence/receipt times
remain separate. Bounds remain inclusive as defined by the existing API; selecting
an end date does not silently extend it to the end of the day. Applied filters
and UTC bounds survive pagination. Archive flags remain booleans during validation.

Verification:

```powershell
npm.cmd run test:dates
npx.cmd playwright test tests/browser/persian-dates.spec.js
```

Unit tests cover known Nowruz/leap fixtures, invalid dates/times, Tehran DST and
independence from process timezone. Browser tests run in Los Angeles time while
asserting Tehran display and outgoing UTC bounds; they also cover archive flags,
pagination, mobile overflow, leap-day keyboard selection, Escape and reset.

The calendar popup uses measured viewport placement: it flips above the input or
shifts inside the available area, follows scrolling, and bounds its own height
with internal overflow. Calendar table rows explicitly override the dashboard's
54px inventory rows while preserving 40px day targets. Browser checks cover the
reported 1366×608 content viewport, 1366×768, 390×700 and 320×568, asserting all
popup edges and its close button stay visible without horizontal page overflow.
