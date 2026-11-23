# Implementation Plan: Injector Device Management Platform

**Status:** Approved delivery plan; limited customer-access scope added 2026-11-18  
**Scope:** Phase 1 MVP from `product-spec.md`  
**Task tracking:** Beads 1.3.4 is initialized with an embedded Dolt database and the `injector` prefix. Tasks and dependencies are imported; `.beads/plan-map.json` maps plan keys to issue IDs. See [development workflow](development-workflow.md).  
**Related specifications:** [`../product-spec.md`](../product-spec.md), [`../technical-spec.md`](../technical-spec.md), [`../design-spec.md`](../design-spec.md)

## 1. Executive summary

Deliver the staff MVP and approved limited customer panel by extending the existing Django/DRF and PostgreSQL backend, replacing its development-only operating assumptions with a controlled, Dockerized production path, and connecting the React/Vite console to the API. Preserve the existing product model and API behavior where it conforms to the specifications. Do not replace Django with FastAPI or copy a generic starter application over the repository.

The current code is a useful scaffold: customer/device/event/release models, API routes, device credential hashing, ingestion and update logic, a sample-data dashboard, a local Compose file, and an interactive onboarding prototype exist. None alone proves production readiness. The plan first introduces Beads tracking and backend engineering foundations, then ships secure staff access and admin data flows, device ingestion and event views, release management, and Docker-based staging/production readiness.

The approved customer portal is limited to administrator-provisioned login and organization-scoped read-only device/connectivity visibility. Licensing, expanded customer self-service, STM32 updates, test-sheet content and AI remain out of MVP scope; device software remains authoritative for offline queues and safe installation; production update rollout depends on resolving and implementing signed release authenticity; and final deployment details depend on selection of the hosting provider and operational targets.

## 2. Sources and authority

### Reviewed sources

- `product-spec.md`: authoritative for user roles, MVP scope, behavior, safety boundaries, acceptance criteria, assumptions, and open product decisions. Key sections: 5–8, 11–15.
- `technical-spec.md`: engineering/deployment direction and repository gaps. Key sections: 2–5, 7–12, 14–16. This is the current technical baseline, but it includes proposed engineering decisions that should not override confirmed product behavior silently.
- `design-spec.md`: authoritative visual and interaction direction, including RTL, tokens, responsive behavior, accessibility and sample-data boundary.
- `README.md`, `backend/README.md`, `prototype/onboarding/README.md`: current setup and implementation descriptions, verified against code where possible.
- `compose.yaml`, `backend/Dockerfile`, `.github/workflows/deploy-prototype.yml`, `package.json`, `src/`, `backend/`: inspected implementation and operational state.
- The prior conversation’s boilerplate inspection: `python-boilerplate/uv-template` is the intended Python tooling baseline. Its tools are not installed or configured in this checkout.

### Repository instructions and existing planning docs (historical assessment)

At the initial plan assessment, no `AGENTS.md`, contribution guide, `docs/boilerplate-assessment.md`, ADR, or existing implementation plan was found in the repository file listing/search. `docs/implementation-plan.md` is therefore the first plan at the requested location. No repository-specific instruction changed the requested format.

### Authority and conflict handling

The product spec controls product behavior and confirmed scope. The design spec controls interface presentation. The technical spec governs proposed implementation/deployment choices when consistent with the other two. Repository behavior is evidence of current state, not a change to the requirements.

Material issues to resolve or manage explicitly:

1. **Release publishing and signing:** Product spec sections 7.5, 8.7 and 15 say an authorized release record is published automatically; product sections 12 and 15 say the existing updater must be reviewed before deciding signing; technical spec sections 5.5 and 16 say production rollout must not be enabled until signed metadata is verified end to end. Plan: preserve automatic publication semantics in the application, but gate any real production device rollout until signing is verified. This is a production rollout blocker, not a blocker for release CRUD or staging simulations.
2. **Staff browser authentication:** Product spec section 7.1 calls for a secure session. Existing API returns DRF tokens; technical spec section 5.4 allows sessions/tokens but prohibits long-lived browser tokens in local storage. Plan: decide and implement secure cookie session + CSRF for the browser, while retaining separate device credentials. This security decision blocks production browser integration but not independent UI work against a mock contract.
3. **Release lifecycle vocabulary:** Product spec section 8.7 lists `available`, `downloading`, `downloaded`, `installing`, `succeeded`, `failed`, and `rolled back`; current model uses `rolled_back`, while README uses `succeeded`. Define canonical API values and labels before frontend integration. Recommend snake_case API enum `rolled_back` with translated UI label “rolled back.”
4. **Event batch receipt time:** Current ingestion updates `Device.last_seen_at` from server time, which aligns with online status. The technical spec recommends each accepted event receive a server receipt timestamp. Current `DeviceEvent.received_at` is `auto_now_add`, which satisfies this. Device check-ins and batch freshness should remain distinct facts.

## 3. Historical repository baseline (initial plan assessment)

### Implemented or reusable

- **Django backend scaffold:** `backend/config/settings.py`, `backend/config/urls.py`, `backend/devices/` use Django 5.2-compatible requirements, DRF, django-filter, PostgreSQL, and token/session authentication classes.
- **Data model:** `backend/devices/models.py` defines Customer, Device, DeviceCredential, DeviceEvent, DeviceFault, SoftwareRelease, UpdateAssignment, and AuditEntry. Unique constraints exist for serial number, `(device,event_id)`, `(device,fault_id)`, and `(release,device)`.
- **API surface:** `backend/config/urls.py` and `backend/devices/views.py` expose staff login/logout, summary, customer/device/event/release resources, device check-in, event batch ingestion, update manifest and update result. Some permissions/search/filter/pagination and idempotency logic exist.
- **Credential provisioning:** `backend/devices/authentication.py` hashes device token values; `backend/devices/management/commands/provision_device.py` provisions credentials. It should be reviewed for rotation/revocation semantics before production use.
- **Admin:** `backend/devices/admin.py` registers operational models and provides search/list controls.
- **Frontend prototype:** `src/App.jsx` and `src/styles.css` implement a visual dashboard, simulated login, sample customer/device/event content, filters, responsive elements and a detail modal. Current app does not fetch the API; login is local state and displayed records are constants.
- **Onboarding walkthrough:** `prototype/onboarding/index.html` is a standalone simulation. `prototype/onboarding/README.md` identifies it as demo/localStorage state, not a connected application.
- **Local Docker:** `compose.yaml` runs PostgreSQL 17 and the API with a named database volume and database health check.
- **Static prototype deploy:** `.github/workflows/deploy-prototype.yml` deploys only `prototype/onboarding` to GitHub Pages.

### Partial, scaffolded, absent, or conflicting

- No Django migrations or tests were present in `backend/`; local docs use `migrate --run-syncdb`.
- `backend/Dockerfile` starts Django `runserver`; `compose.yaml` runs migrations on every API container start. This is development-only and conflicts with `technical-spec.md` production guidance.
- Dependencies are in `backend/requirements.txt`; no `pyproject.toml`, `uv.lock`, Ruff/MyPy/Pytest/pre-commit config or backend CI was found. `package.json` uses floating `latest` for major frontend packages and no lockfile was listed.
- Backend docs say Python 3.11+ and PostgreSQL 15+; technical spec targets Python 3.12/PostgreSQL 17. Confirm the intended floor and align docs/build/test images. Recommend the technical spec target unless provider constraints require otherwise.
- Staff login creates/reuses a non-expiring DRF token (`staff_login` in `backend/devices/views.py`) and logout deletes it. This does not establish a secure browser session lifecycle; UI currently does not call it.
- `CustomerViewSet`/`DeviceViewSet`/`EventViewSet`/`ReleaseViewSet` exist in `backend/devices/views.py`, but model/route presence is not equivalent to full product authorization, validation, concurrency, audit, or UI workflows.
- `backend/devices/models.py` uses Django's default user and its `is_staff`/`is_superuser` split. Product roles are super administrator and support; confirm whether Django flags/groups are the intended role mapping before building staff account UX.
- `backend/devices/views.py` batch ingestion logic is present and deduplicates event IDs, but validation limits, transaction grouping, concurrency semantics, last-seen handling for invalid/duplicate batches, audit behavior and malformed/conflict edge cases require tests and review.
- Update registry and assignment logic exist; signature verification does not. The currently inspected API manifest returns SHA-256 and package URL only.
- Audit model exists, but audit coverage and immutability for all privileged actions are not established by model existence.
- `src/App.jsx` includes fake login, local-only theme state, hard-coded sample data and some “coming soon” actions. Device detail, customers, logs and releases are not connected CRUD flows.
- No production static serving, production API server, image registry workflow, provider deployment, backup/restore automation, health endpoints, structured logging or monitoring config was found.
- `technical-spec.md` is untracked in the current worktree (`git status` reported `?? technical-spec.md` at inspection), so it needs to be included in the eventual documentation commit if intended to be versioned. This plan does not stage it.

### Initial inspection limits

Inspected the tracked source tree, key backend models/serializers/permissions/authentication/admin/views/settings/routes, frontend app/bootstrap/package, Compose/Docker setup, READMEs, product/technical/design specs, and the existing GitHub Pages workflow. No packages were installed, no tests were run, and no provider, device-side updater/client repository, deployment account, production secrets, or CI execution was available. Source files with Persian UI strings show encoding mojibake in terminal output; actual rendered browser encoding was not verified. Beads CLI/setup is absent from the repository and was not invoked.

### Scope-alignment reinspection before customer implementation (2026-11-18)

The paragraphs above describe the original assessment, not current task completion. Current status belongs in Beads. Source reinspection found committed-style migration files and PostgreSQL tests in the worktree, pyproject.toml/uv.lock, a secure staff cookie-session/CSRF/login-limiter implementation, IsStaffUser/IsSuperAdministrator permissions, the staff-users API and src/StaffUsers.jsx, src/LiveConsole.jsx, src/api.js and browser shell tests. src/App.jsx selects the live console unless explicit demo mode is enabled. None of these observations asserts unrun tests passed during this documentation task.

There is no User-to-Customer membership, customer login role, scoped customer device API or customer panel yet. Staff login currently rejects non-staff accounts and session restoration is staff-only. Preserve these staff security boundaries while adding a separate eligible customer role. Current tests rejecting arbitrary nonstaff users remain valid; add positive customer-membership cases rather than allowing every Django user to sign in.

prototype/onboarding/index.html is a browser-only staff onboarding simulation with localStorage and simulated connection/update actions; its customers page explicitly says customer login is deferred. Its visual layout is the approved reference, while this new scope supersedes that old copy. No existing production customer flow was found to wire up unchanged. Extend the connected console with the same Persian RTL visual language; do not edit or turn the sample prototype into a live portal in this scope-alignment task.

Current staff authentication/permissions, migrations, DATA-001 and UI-001 have closed Beads history. Customer implementation is new work; leave completed issues closed and depend on them. The worktree contains extensive pre-existing modifications/untracked files. This task changes documents and Beads only; no application code, secret .env files or production data is changed.

## 4. Requirements and gap analysis (original gaps plus approved extension)

| Requirement (source) | Current repository state | Reuse / change | Planned task(s) | Dependency or uncertainty |
|---|---|---|---|---|
| Track work as reviewable product tasks (requested workflow change) | No Beads config/state found | Add Beads locally/repo per team choice; keep IDs stable in plan | `OPS-001` | Confirm CLI/init and whether task state is committed/shared; setup can use local defaults meanwhile |
| Django/DRF + PostgreSQL product service (product §6, tech §2–4) | Scaffold and models/routes exist | Extend existing service; no framework rewrite | `ENG-001`, domain slices | Confirm user role mapping and target Python/Postgres floors |
| Reliable schema/migrations (product §9, tech §6–7) | No migration files found; `--run-syncdb` used | Introduce committed migrations and controlled migration workflow | `ENG-002`, `OPS-004` | Existing development DB may require baseline strategy if real data exists; inspect before migration |
| Secure staff sign-in, roles, revocation, audit (product §§5, 8.1) | API login returns persistent token; permission classes use `is_staff`/`is_superuser`; frontend fake login | Extend or replace browser auth with secure session + CSRF; preserve device auth separately; audit privileged changes | `AUTH-001`, `AUTH-002` | Cookie/session design decision is required before production frontend integration |
| Customer/device registration/search/archive (product §§7.2, 8.2–8.3) | Models/admin and DRF viewsets exist; dashboard sample-only | Extend validations, role checks, searchable API and wire UI flows | `DATA-001`, `UI-002` | Confirm required contact/address fields against model and existing UI |
| Device identity, check-in and event ingestion (product §§7.4, 8.4–8.5) | Device credential model/auth and routes exist; ingestion logic present | Harden/test idempotency, payload constraints, timestamp semantics and responses; connect client when available | `DEVICE-001`, `DEVICE-002` | Device client source/protocol is not in repository; API compatibility must be reviewed with device owner |
| Connectivity and dashboard metrics (product §§7.3, 8.6) | Summary API exists; UI values are hard-coded | Reuse summary and derived online threshold; connect live data, explicit freshness/errors | `UI-003` | 15-minute threshold confirmed; no live refresh cadence requirement specified |
| Event/fault history with late arrival and filters (product §§7.4, 8.5) | Event/fault models and read-only event endpoint exist | Add missing filters/detail response and validate out-of-order projection; build UI history | `DEVICE-002`, `UI-004` | Product says occurrence time governs current fault; tie-breaking for equal timestamps is technical detail to define |
| Python release registry, targeting, results, rollback (product §8.7) | Models/routes/views exist; no signed metadata; UI absent | Extend release API/form and assignments UI, audit, canonical states; hold production delivery on signing | `REL-001`, `REL-002` | Provider/package host and device updater/signing support open; production rollout blocked pending verification |
| Persian RTL, responsive, themes, accessibility (design; product §8.8) | Visual prototype/style exists; RTL-oriented layout and theme class; no persistence/live states | Reuse styling/components; fix encoding if confirmed; add stateful accessible forms/data flows and tokenized themes | `UI-001` through `UI-005` | Validate fonts/assets and screen reader/contrast in browser |
| Dockerized deployment and provider operations (tech §§7–9) | Development Compose + runserver Dockerfile only | Create production image, one-off migration, health, config/secrets, static serving and provider runbook | `OPS-002`–`OPS-005` | Provider topology, managed DB, TLS and secret mechanism not selected |
| Reproducible Python workflow from uv-template (tech §10) | requirements.txt; no lock, tests, lint/type tool config | Adapt `uv`, pyproject/lock, Ruff, progressive MyPy, Pytest, pre-commit/Make commands | `ENG-001`, `ENG-003` | Python version choice; avoid blindly copying generic template defaults |
| CI build/check/release controls (tech §11) | Only Pages workflow for onboarding prototype | Add PR checks and separate gated production release workflow | `OPS-003`, `OPS-005` | Image registry/provider and protected-environment features unknown |
| Backups, retention, observability and service targets (product §10, tech §9) | Not configured; retention/RPO/RTO/volume open | Define minimum staging/prod dashboards/backups and document measurable targets before launch | `OPS-004`, `OPS-005` | Capacity and operations owner input needed before production |
| Limited customer device panel (approved 2026-11-18; product §§5.3–5.4, 7.6) | No account membership/customer auth or routes; staff sessions/client reusable | Add membership, customer sessions, admin provisioning, scoped APIs and panel | `CUST-001`–`CUST-007` | Approved now; preserve staff/device boundaries |
| Expanded customer self-service, licensing, test sheets/AI, firmware updates (product §§4, 6) | Outside approved scope | Keep explicitly deferred | Deferred | Requires a separate product decision |

## 5. Implementation approach and key decisions

### Reuse strategy

1. Keep Django/DRF and current relational domain models. Refactor only where tests or product gaps demonstrate need; retain the modular-monolith topology in `technical-spec.md`.
2. Keep existing public device endpoint behavior compatible until device-client owners approve a versioned change. First document payload schemas and capture them in contract tests.
3. Use the `uv-template` for its Python dependency/quality workflow, CI conventions and Docker lessons. Do not import its generic sample app or overwrite the React console.
4. Keep the onboarding prototype and GitHub Pages workflow separate from production; it can serve as a manual product-flow reference, not live application code.
5. Use product design tokens and existing React/CSS as a starting point; split `src/App.jsx` into domain components as real flows are added, without introducing a new UI framework without need.

### Proposed technical decisions

- Use secure, same-site HttpOnly cookie sessions for the browser dashboard, with CSRF on state-changing requests. Keep device credentials as a separate device-only authentication scheme. This resolves the product's secure-session journey and avoids browser localStorage bearer tokens. Confirm exact same-origin deployment when selecting provider; CORS is restricted if origins differ.
- Map the product roles explicitly. Proposed mapping: Django superuser to super administrator and a controlled Django group/permission set to support. Do not grant every `is_staff` account identical write permissions just because existing `IsAdminUser` allows them.
- Introduce actual migrations before data-dependent development. Inspect whether any non-disposable database exists before baselining; the repository description currently implies prototype data, but this is not a verified production-data inventory.
- Separate event facts (immutable event rows) from derived current fault state. Preserve current model shape if tests prove its invariant behavior; otherwise add deterministic occurrence-time ordering and tie-break rule.
- Keep release auto-publication in app semantics. Enforce a rollout gate outside the user-facing product or in a deliberate release state until signature verification is implemented and approved. This preserves staging product acceptance while avoiding unsigned production update delivery.
- Use the current online threshold of 15 minutes. Keep configured value visible in API summary/operational documentation.
- Use provider-managed PostgreSQL where available; if not, document durable storage and tested backups for a private database container. Do not expose DB port publicly.
- Keep separate deployment artifacts: production API image and frontend static build/image. Do not use GitHub Pages for authenticated production console.

### Assumptions and open questions

- **Assumption, nonblocking:** Development DB is disposable and contains no customer/device records requiring a migration-baseline import. Validate before first production migration.
- **Open, blocks production authentication:** Does the chosen host permit same-origin console/API and secure cookie sessions? If not, document trusted origins and CSRF/CORS policy.
- **Open, blocks production device rollout:** What signing protocol/key custody can the current device updater support? Device source and owner review required.
- **Open, blocks provider-specific deployment task only:** Which hosting provider/product and image registry will be used?
- **Open, blocks capacity/SLO setting only:** Expected device fleet, event rate/retention, availability, latency, RPO/RTO, backup owner and alert destination?
- **Open, required before device-client release but not scaffold tests:** Is there an existing deployed device API contract/version and backward compatibility window?
- **Open, nonblocking for core MVP:** Are event exports required now? Product spec defers them pending operational need.
- **Open, Beads setup:** Is Beads project-local state sufficient, or should issue state be committed/shared? Proposed initial setup should follow the Beads tool's repo guidance and avoid committing generated state/secrets without a team choice.

## 6. Dependency-ordered milestones and tasks

Relative sizing: **S** one focused change/review; **M** several files or a complete vertical slice; **L** cross-cutting work requiring staged review. Beads IDs are stable plan keys proposed for issue creation. If the installed Beads CLI generates its own IDs, keep these IDs as labels/plan references and record the mapping rather than overwriting CLI IDs.

### Milestone 0 — Establish task tracking and executable backend foundation

#### OPS-001 — Initialize Beads tracking for MVP work (S)

- **Outcome / refs:** Track implementation tasks and dependencies in Beads; requested by user. Workflow support for technical spec §10.
- **Depends on:** None.
- **Existing paths:** `technical-spec.md`, `README.md`, `.gitignore`.
- **Proposed paths:** Beads-managed repository metadata/config only after checking the installed Beads version's recommended setup; optionally a short `docs/development-workflow.md` if Beads usage needs team-specific documentation.
- **Work:** Check/install Beads through the approved team environment process; initialize project-local database/config according to Beads guidance; create epic/milestone issues corresponding to this plan; link dependency IDs; define a policy for generated state in Git and ignore rules. Add this plan path to the project documentation. Do not put product work or application runtime dependencies in Beads.
- **Acceptance:** `bd` (or the selected Beads command) reports the repository project; tasks for all milestones can be listed with dependencies; one sample task can transition status; repository policy states whether issue state is shared/committed; no secrets or unrelated file changes.
- **Verification:** Manual CLI check and `git status`; review Beads-generated files before committing.
- **Risks/questions:** CLI is not currently present/configured; tracking mode and generated-file policy need team preference. This does not block code implementation if Beads cannot be provisioned immediately, but blocks claiming Beads workflow is active.

#### ENG-001 — Establish locked Python project tooling (M)

- **Outcome / refs:** Reproducible development/build dependencies; tech spec §§2, 10.
- **Depends on:** None (may track in Beads after OPS-001).
- **Existing paths:** `backend/requirements.txt`, `backend/Dockerfile`, `backend/README.md`, `technical-spec.md`.
- **Proposed paths:** `backend/pyproject.toml`, `backend/uv.lock`, backend test config.
- **Work:** Choose Python 3.12 as technical spec baseline unless provider support disproves it; declare current Django/DRF/filter/PostgreSQL/CORS deps and dev tools in one project config; generate committed lock; document `uv sync` workflow; avoid floating versions and ensure production install excludes dev tools.
- **Acceptance:** Clean backend checkout can install locked runtime and dev groups with the documented `uv` commands; dependency versions resolve to the stated framework/database compatibility; requirements source is no longer ambiguous.
- **Verification:** CI later; initially run `uv lock --check`/sync in a clean environment and Django system check.
- **Risks/questions:** Existing local requirements allow broad version ranges; do not update major framework versions as incidental migration.

#### ENG-002 — Add database migrations and remove syncdb dependence (M)

- **Outcome / refs:** Reproducible schema deployment; product §9, tech §§6–7.
- **Depends on:** ENG-001.
- **Existing paths:** `backend/devices/models.py`, `backend/config/settings.py`, `compose.yaml`, `backend/README.md`.
- **Proposed paths:** `backend/devices/migrations/0001_initial.py` and subsequent migration files.
- **Work:** Inspect existing target DBs before selecting initial migration baseline; generate migrations for existing models; review constraints/index names and migrate from empty PostgreSQL; update docs. Do not use `--run-syncdb` for product tables.
- **Acceptance:** Fresh PostgreSQL database reaches current model schema by `manage.py migrate`; migration check reports no uncommitted model changes; data-preserving path is documented if any persistent DB already exists.
- **Verification:** Migration tests on PostgreSQL, fresh DB apply, `makemigrations --check`.
- **Risks/questions:** If an existing non-disposable database has syncdb-created tables, migration baseline must be rehearsed against a copy before rollout.

#### ENG-003 — Add focused backend test harness and critical domain tests (M)

- **Outcome / refs:** Make behavioral changes safe; product acceptance criteria §11, tech §12.
- **Depends on:** ENG-001, ENG-002.
- **Existing paths:** `backend/devices/views.py`, `serializers.py`, `authentication.py`, `permissions.py`, `models.py`.
- **Proposed paths:** `backend/tests/` or per-app `tests/` modules, pytest configuration in `backend/pyproject.toml`.
- **Work:** Configure pytest against PostgreSQL; add behavior tests first for device credential auth/revocation, unique serial/event constraints, duplicate/conflicting event IDs, out-of-order fault state, update target/version eligibility, and access-role boundaries. Prefer API contract tests over implementation-mock tests.
- **Acceptance:** Tests fail against the relevant broken behavior, pass against current intended behavior, and run from one documented command using PostgreSQL.
- **Verification:** Pytest locally/CI after OPS-002 establishes CI.
- **Risks/questions:** Existing code may expose latent mismatches. Fix product behavior in subsequent domain tasks, not by weakening assertions.

### Milestone 1 — Secure identity and customer/device administration

#### AUTH-001 — Define and implement staff browser session lifecycle (L)

- **Outcome / refs:** Secure sign-in/out journey and session revocation; product §§7.1, 8.1; tech §5.4.
- **Depends on:** ENG-001, ENG-003.
- **Existing paths:** `backend/devices/views.py` (`staff_login`, `staff_logout`), `backend/config/settings.py`, `backend/config/urls.py`, `src/App.jsx` (`Login`, `App`).
- **Proposed paths:** Auth service/serializer/tests under existing backend app; frontend API/auth client module in `src/`.
- **Work:** Select same-origin secure session cookie + CSRF for browser; implement expiry/rotation/revocation and inactive-account rejection; retain device auth as separate scheme; avoid long-lived localStorage tokens; align login response with UI; add safe failure states and rate limiting. Audit sign-in/out outcomes without secrets.
- **Acceptance:** Valid staff can sign in and access protected API; invalid/inactive/unauthorized credentials receive generic denial (customer access is added separately by CUST-002); session expires/revokes on logout; CSRF blocks unsafe cross-origin cookie request; no browser token is stored in localStorage; login limits apply.
- **Verification:** Backend auth/CSRF tests and manual browser login, refresh, logout, expiry, keyboard flow.
- **Risks/questions:** Requires final origin/cookie policy for provider. Do not block unrelated admin CRUD mocked work, but block production dashboard integration.

#### AUTH-002 — Enforce support and super-administrator permissions with audit coverage (M)

- **Outcome / refs:** Server-side role authorization and audit; product §§5, 8.1.
- **Depends on:** AUTH-001, ENG-003.
- **Existing paths:** `backend/devices/permissions.py`, `backend/devices/views.py`, `backend/devices/models.py` (`AuditEntry`), `backend/devices/admin.py`.
- **Proposed paths:** Permission matrix documentation/tests; narrowly scoped service helpers if needed.
- **Work:** Make explicit matrix for staff read, customer/device writes, user management, release publish/withdraw/rollback, device provisioning, and audit access. Map superadmin/support deliberately; prevent blanket `IsAdminUser` from granting privileged writes. Audit actor/action/target/outcome for successful and denied sensitive actions without credentials/payload secrets. Limit admin access consistently.
- **Acceptance:** Support can perform only allowed reads and any explicitly granted actions; superadmin can perform specified administration; anonymous/device credentials cannot access staff APIs; privileged changes create auditable entries.
- **Verification:** Matrix-driven API permission tests and Django admin manual review.
- **Risks/questions:** Product says update permission can optionally be explicitly granted; MVP default should keep support read-only until an owner decides otherwise.

#### DATA-001 — Harden customer and device administration contracts (M)

- **Outcome / refs:** Customer/device registration, search, filter, archive; product §§7.2, 8.2–8.3.
- **Depends on:** ENG-002, AUTH-002.
- **Existing paths:** `backend/devices/models.py` (`Customer`, `Device`), `backend/devices/serializers.py`, `backend/devices/views.py` (`CustomerViewSet`, `DeviceViewSet`), `backend/devices/admin.py`.
- **Proposed paths:** Focused domain/service functions only for audited changes; API contract docs.
- **Work:** Reconcile fields to product requirements (address/region/notes, registration/deployment contact); normalize searchable values; implement duplicate serial validation with useful error; archive semantics and audited reassignment; enforce allowed writes; ensure search/filter by customer/model/connectivity/faults. Preserve server pagination and stable ordering.
- **Acceptance:** Authorized admin can create/edit/archive customer and device; duplicate serial returns field-level conflict; support read/search works; archived records remain in history and are excluded/included by documented filters; assignment changes are auditable.
- **Verification:** PostgreSQL API tests for constraints/search/archive/permissions plus manual admin API requests.
- **Risks/questions:** Customer mandatory fields beyond organization/contact are open; use current model minimum pending product owner confirmation.

#### UI-001 — Refactor prototype into accessible application shell and API client boundary (M)

- **Outcome / refs:** Retain established design while preparing real screens; design spec; product §8.8.
- **Depends on:** ENG-003 (API contract tests), AUTH-001 contract decision.
- **Existing paths:** `src/App.jsx`, `src/main.jsx`, `src/styles.css`, `index.html`, `package.json`.
- **Proposed paths:** `src/api/`, `src/components/`, `src/features/`, lockfile, shared locale/theme utility.
- **Work:** Break monolithic `App.jsx` into shell, navigation, and reusable foundation components as needed; establish API base/error/loading conventions and auth context; externalize Persian strings enough for future localization; persist theme preference; check font loading/UTF-8 and set semantic RTL/LTR direction rules; add loading, empty, error, stale states and keyboard/focus behavior. Do not connect fake login as real auth.
- **Acceptance:** App shell can render loading, unauthenticated, authenticated, error and empty states; Persian layout remains RTL while serial/version/code remain LTR; theme survives reload; no fake login grants API access; existing responsive layout retained.
- **Verification:** Production frontend build, keyboard/manual responsive checks, RTL and screen-reader labeling review.
- **Risks/questions:** Existing Persian strings appear mojibaked in terminal inspection; confirm actual source encoding before mass rewriting.

#### UI-002 — Connect staff login and customer/device management screens (M)

- **Outcome / refs:** Core staff onboarding; product journeys §§7.1–7.2 and design spec.
- **Depends on:** AUTH-001, AUTH-002, DATA-001, UI-001.
- **Existing paths:** `src/App.jsx`, `src/styles.css`, backend auth/customer/device routes.
- **Proposed paths:** `src/features/auth/`, `src/features/customers/`, `src/features/devices/`.
- **Work:** Replace simulated Login with API session; build customer/device create/edit/archive workflows; connect search, filter and pagination; show server validation; add pending/empty/failure/success feedback; ensure role-based UI affordances match server permissions.
- **Acceptance:** Staff login gates data; authorized admin registers customer/device; duplicate serial is shown inline; support can search/open records; API denial is visible and does not leave stale success UI; no seed sample records appear in live mode.
- **Verification:** API/UI integration tests for auth and CRUD where harness permits; manual mobile/desktop keyboard walkthrough.
- **Confirmed requirement:** Staff provisioning includes a super-administrator-only application UI, already represented by src/StaffUsers.jsx and its API. Customer account provisioning is added separately by CUST-003; neither role permits public registration.

### Milestone 2 — Device events, health, and operations

#### DEVICE-001 — Specify and harden device credential/check-in contract (M)

- **Outcome / refs:** Authenticated status check-ins and revocable identity; product §§7.4, 8.4.
- **Depends on:** ENG-002, ENG-003.
- **Existing paths:** `backend/devices/authentication.py`, `models.py` (`DeviceCredential`, `Device`), `management/commands/provision_device.py`, `views.py` (`device_check_in`), `serializers.py`.
- **Proposed paths:** API schema/examples; rotation command/service and tests.
- **Work:** Verify digest comparison, revoke and rotate semantics, one-time secret output, audit, invalid/archived device handling, rate limits and strict check-in schema. Define response/auth contract with device owner; check-in updates last-seen from server receive time only. Document TLS requirement and credential handling.
- **Acceptance:** Valid credential checks in only its device; revoked credential fails; replacement token works and old token fails; last_seen updates server-side; malformed/oversized input rejected; secret is never retrievable from DB/log.
- **Verification:** Authentication/check-in API tests, credential rotation manual CLI check.
- **Risks/questions:** Device-side client is absent, so backward compatibility and rollout sequencing require device owner sign-off.

#### DEVICE-002 — Make event batch ingestion and fault projection robust (L)

- **Outcome / refs:** Durable retry-compatible immutable ingestion; product §§7.4, 8.4–8.5; technical §5.3.
- **Depends on:** ENG-002, ENG-003, DEVICE-001.
- **Existing paths:** `backend/devices/models.py` (`DeviceEvent`, `DeviceFault`), `serializers.py` (`EventIngestSerializer`), `views.py` (`ingest_events`, `event_matches_payload`).
- **Proposed paths:** Domain service for atomic/idempotent event processing; OpenAPI/event examples.
- **Work:** Enforce max batch/body/metadata limits, timestamps, identifiers and enum constraints; define per-event accepted/duplicate/rejected result semantics; ensure conflicting ID reuse cannot mutate facts; handle race inserts; update latest fault by occurred_at with deterministic equal-time tie-break; retain receipt time; separate device last-seen semantics; choose partial-batch transaction behavior and document it. Check acknowledgement rules against device queue.
- **Acceptance:** Repeated identical event is duplicate with same ID; conflicting payload is rejected and original remains unchanged; late older fault remains in history without replacing newer fault; each accepted event has server receipt timestamp; batch outcomes are per-event and retry-safe; untrusted serial alone cannot authenticate.
- **Verification:** PostgreSQL transaction/concurrency tests and contract examples, including out-of-order and invalid mixed batches.
- **Risks/questions:** Contract compatibility with deployed devices is open. Partial batch acceptance should remain if the client reliably handles per-event results; otherwise revise with protocol owner.

#### UI-003 — Connect fleet summary, freshness, connectivity and device detail (M)

- **Outcome / refs:** Fleet overview, online estimate and useful device detail; product §§7.3, 8.6.
- **Depends on:** UI-001, UI-002, DEVICE-001, DATA-001.
- **Existing paths:** `src/App.jsx` dashboard constants/modal, `backend/devices/views.py` (`dashboard_summary`, DeviceViewSet), `backend/config/settings.py` online window.
- **Proposed paths:** Device list/detail feature modules and typed API response definitions.
- **Work:** Consume summary/device APIs; show 15-minute online threshold basis and generated freshness; server-side search/filter/pagination; show software, customer/contact, last-seen, active-fault count; implement stale/loading/error/empty states; preserve Persian RTL and LTR identifiers.
- **Acceptance:** Counts match API fixtures; stale values have an explicit timestamp; device list search spans serial/customer/model; online/offline filters align with configured threshold; detail opens correct device and does not claim server status proves safe test execution.
- **Verification:** API/UI tests for query and state behavior; manual viewport and accessibility check.
- **Risks/questions:** Refresh/poll interval not specified; begin with explicit manual refresh or modest documented polling only if needed.

#### UI-004 — Connect event and fault history with delayed-delivery context (M)

- **Outcome / refs:** Searchable event review and active/resolved fault visibility; product §§7.3–7.4, 8.5–8.6.
- **Depends on:** DEVICE-002, UI-001, DATA-001.
- **Existing paths:** `src/App.jsx` sample `events`, tabs and modal; `backend/devices/views.py` EventViewSet and device events action; `backend/devices/serializers.py`.
- **Proposed paths:** `src/features/events/`, event detail/list component.
- **Work:** Connect event list/device history, filters (customer/device/code/state/time range), pagination, occurrence and receipt timestamps, fault state and stable code. Clearly mark delayed receipt where timestamps materially differ; display only approved metadata fields and never secrets.
- **Acceptance:** Staff can filter and page real events; delayed event shows occurrence and server receipt time; older event remains in history; active/resolved status reflects device report; empty/error/loading states are clear.
- **Verification:** Query/filter API tests plus manual offline-delivery scenario using fixture/device simulator only if available.
- **Risks/questions:** Event export is deferred unless product owner elevates it; metadata display allowlist must be established.

### Milestone 3 — Release workflow and controlled update readiness

#### REL-001 — Harden release metadata, targeting, audit and lifecycle contract (L)

- **Outcome / refs:** Release registry and per-device rollout state; product §7.5, §8.7; technical §5.5.
- **Depends on:** ENG-002, ENG-003, AUTH-002, DEVICE-001.
- **Existing paths:** `backend/devices/models.py` (`SoftwareRelease`, `UpdateAssignment`), `serializers.py`, `views.py` (`ReleaseViewSet`, eligibility, manifest, update_result), `backend/README.md`.
- **Proposed paths:** Release domain service, API schema, signing protocol record when approved.
- **Work:** Validate HTTPS URL, digest, semantic version, target exclusivity/compatibility and immutable published metadata; resolve canonical lifecycle enum; audit create/publish/withdraw/rollback; make assignment state transitions/idempotency explicit; preserve older metadata; ensure archived devices excluded and newly registered devices only receive all-device releases. Add signature fields/verification only after device protocol decision; maintain a feature/operational gate that prevents production rollout while unsigned.
- **Acceptance:** Superadmin can publish to all compatible or explicit devices; incompatible devices receive no manifest; release can be withdrawn and prior release reassigned with reason/audit; state changes are traceable; production delivery is disabled until valid signature verification is configured.
- **Verification:** API/domain tests for target matrix, URL/digest/schema, withdrawals, rollback, duplicate result and permissions; staging integration when device client available.
- **Risks/questions:** Product says release record creation publishes automatically; technical safety gate constrains actual production delivery. Signing support, key custody and package host are blocking production rollout.

#### REL-002 — Build release and rollout management UI (M)

- **Outcome / refs:** Admin creates release and inspects outcomes; product §§7.5, 8.7.
- **Depends on:** UI-001, AUTH-002, REL-001.
- **Existing paths:** `src/App.jsx` update navigation placeholders; `src/styles.css`; release/assignment API routes.
- **Proposed paths:** `src/features/releases/` and release form/detail components.
- **Work:** Build release form with HTTPS URL, version, SHA-256, compatibility, notes and all-vs-selected targeting; show confirmation of automatic publication semantics; display per-device status/history; expose withdrawal and audited rollback only to authorized admins; label signing gate and avoid suggesting a device is forced to install.
- **Acceptance:** Admin can create a valid release and see selected target; validation errors are actionable; support can inspect but cannot publish/rollback; rollout results distinguish available/downloading/installed/failure/rollback; no claim of signature-secured update before verified.
- **Verification:** Form/API integration and permission tests; manual publish-to-staging flow.
- **Risks/questions:** Product wording around all-compatible default versus explicit target must be reconciled with current UI selection; avoid accidental broad rollout with explicit target confirmation.

#### REL-003 — Verify signed update metadata with device updater (L, conditional)

- **Outcome / refs:** Publisher authenticity for remote package delivery; product §8.7 and open decisions §12; technical §§5.5, 16.
- **Depends on:** REL-001; device source/protocol owner input.
- **Existing paths:** Manifest in `backend/devices/views.py`; `SoftwareRelease` fields in `backend/devices/models.py`; no device updater repository was found.
- **Proposed paths:** Signing/verifier implementation and test vectors in backend and device repositories as agreed.
- **Work:** Inspect actual updater; select signature format/key custody/rotation/revocation; sign immutable release manifest; publish trusted verification key to devices safely; verify signature before download/install; test corruption, substitution, stale/replayed manifest and rotation. Do not add unverifiable API fields alone.
- **Acceptance:** Production device refuses a modified or unsigned manifest/package and accepts an authorized signed release; key rotation/recovery is documented and tested.
- **Verification:** Cross-repository test vectors and hardware/device staging test.
- **Risks/questions:** Blocked until device source/updater support and key owner are available; no safe substitute can be inferred from SHA-256 alone.

### Milestone 4 — CI, Docker, provider deployment and production acceptance

#### OPS-002 — Add repository CI for backend and frontend checks (M)

- **Outcome / refs:** Repeatable quality/build gates; technical §§10–12.
- **Depends on:** ENG-001, ENG-003; UI-001 package lock/config availability.
- **Existing paths:** `.github/workflows/deploy-prototype.yml`, `backend/requirements.txt`, `package.json`.
- **Proposed paths:** `.github/workflows/ci.yml`, backend/frontend lockfiles, config.
- **Work:** Add PR workflow with locked Python sync, Ruff, progressive MyPy, PostgreSQL-backed pytest, frontend install/build, backend image build and dependency scan. Keep Pages workflow independent and path-limited. Scope workflow permissions minimally; no production secrets in CI.
- **Acceptance:** PR checks run on relevant paths and fail on lint/test/build errors; Pages deploy remains only for onboarding prototype; CI artifacts identify commit.
- **Verification:** Trigger workflow on draft branch/PR; inspect permissions and logs for secret exposure.
- **Risks/questions:** GitHub Actions is verified as current CI provider from Pages workflow; registry/release credentials remain out of scope here.

#### OPS-003 — Create production API and frontend container artifacts (M)

- **Outcome / refs:** Dockerized portable services; technical §§7.1–7.3.
- **Depends on:** ENG-001, ENG-002, OPS-002.
- **Existing paths:** `backend/Dockerfile`, `compose.yaml`, root `package.json`, `.gitignore`.
- **Proposed paths:** production `backend/Dockerfile`, `backend/.dockerignore`, frontend `Dockerfile` or static artifact workflow, Compose development profile changes.
- **Work:** Multi-stage/minimal API build with locked dependencies, non-root runtime, Gunicorn/production WSGI, static collection as required, no secrets/dev dependencies; frontend production build/serve independently; add internal health/readiness endpoints; keep dev runserver profile explicitly dev-only; remove production migration-on-every-replica startup and `--run-syncdb`; configure container health checks and private DB network. Document image tags/digests and graceful termination.
- **Acceptance:** API image runs non-root with production server; frontend build serves static console; API/DB are private except public API ingress; health endpoints distinguish process/live from DB-ready; containers restart without losing DB data; no secret or local env file is in image.
- **Verification:** Docker build/run smoke test, inspect image user/layers, API health with DB up/down, frontend build.
- **Risks/questions:** Provider may require different artifact entrypoint; retain OCI portability and defer provider manifests.

#### OPS-004 — Add safe settings, configuration, migration and local runbooks (M)

- **Outcome / refs:** Safe repeatable local/staging startup; technical §§7.4–7.5, 8.
- **Depends on:** ENG-002, OPS-003.
- **Existing paths:** `backend/config/settings.py`, `.env.example`, `backend/.env.example`, `compose.yaml`, `README.md`, `backend/README.md`.
- **Proposed paths:** one canonical environment example, management/release command docs, health checks.
- **Work:** Consolidate duplicate env examples; validate production secret/debug/hosts/origins; set trusted proxy/CORS/CSRF/cookie settings explicitly; create one-off migration command/job; add documented superuser and device provisioning procedures; remove unsafe production defaults; clarify local compose versus provider deployment; add database restore/backup procedure placeholder until provider chosen.
- **Acceptance:** Production config refuses DEBUG/default secret/wildcard host; local setup is reproducible from documented commands; migrations run once explicitly; DB is not publicly exposed; no secrets committed.
- **Verification:** Django deployment checks for staging settings, compose config validation, fresh local DB bootstrap and manual secret scan.
- **Risks/questions:** Same-origin and proxy behavior depend on provider; verify before setting HSTS/trusted proxy.

#### OPS-005 — Select provider deployment and operational controls (L, conditional)

- **Outcome / refs:** Production hosting, backups, monitoring, recovery; product §10 and open decisions §12; technical §§7–9, 15–16.
- **Depends on:** OPS-003, OPS-004; owner/provider inputs.
- **Existing paths:** `technical-spec.md`, `compose.yaml`, current Pages workflow for separation reference.
- **Proposed paths:** provider-specific deployment manifest/workflow, operations runbook, alert/backup config.
- **Work:** After provider selection, document registry, networking, domains/TLS, secret injection, managed-vs-container PostgreSQL, storage, health check, migration job, deployment/rollback, backups/PITR, restore exercise, log/metric collection, alert route, on-call owner and staging/prod separation. Set measurable capacity/SLO/RPO/RTO/retention targets based on fleet estimates.
- **Acceptance:** Staging deploy can be recreated from reviewed configuration; HTTPS and health checks pass; backup restore is rehearsed; image rollback works; alerts cover availability, 5xx, DB capacity, ingestion failures and backup freshness; targets and owners are recorded.
- **Verification:** Staging smoke checklist and timed restore/rollback exercise.
- **Risks/questions:** Blocked on provider, fleet, retention, and operations owner decisions; do not make up uptime guarantees.

#### UI-005 — Remove sample-only operational state and verify production console (M)

- **Outcome / refs:** Live dashboard accurately represents server state; product §§8.6, 11; design phase boundary.
- **Depends on:** UI-002, UI-003, UI-004, REL-002, OPS-004, CUST-007.
- **Existing paths:** `src/App.jsx` constants and local simulated state, `src/styles.css`, root `README.md`.
- **Proposed paths:** production runtime config and smoke test scripts if needed.
- **Work:** Ensure live mode has no sample fallback presented as production data; preserve explicit prototype mode only when labeled; handle expired sessions, API outage, stale summary, empty results, pagination and failed mutations; validate RTL/LTR identifiers, touch targets, keyboard/focus, reduced motion, theme persistence and production assets.
- **Acceptance:** A clean production console shows empty/live API state without sample customers/devices; API outage is visibly distinct from empty fleet; no simulated button reports a successful backend action; core workflows pass on desktop/mobile.
- **Verification:** Browser acceptance walkthrough against staging plus accessibility/manual responsive review.
- **Risks/questions:** Requires provider origin/runtime config and real staging data or controlled fixtures.

### Approved customer-access increment — CUST-EPIC (2026-11-18)

**Decision:** Super-administrator-provisioned customer login/logout and a dedicated read-only own-organization device/connectivity panel are in MVP. One organization per account, multiple accounts per organization. Customers never receive staff privileges. Product sections 5.4 and 7.6, technical section 5.6 and the customer design section define the role matrix, safe fields, routes and state behavior. The implementation is now present; current task status and verification remain authoritative in Beads, with handoff details in section 11.

**Scope tracking:** CUST-000 covers the documentation/Beads alignment only. CUST-001 through CUST-007 implement and verify the capability; their IDs are in .beads/plan-map.json. Add tests with each behavior slice; CUST-006 is integrated acceptance, not deferred security hardening. No existing completed task is reopened. UI-005 also depends on CUST-007 so final MVP acceptance cannot omit customer access.

#### CUST-001 — Add customer account membership and additive migrations

- **Depends on:** ENG-002, AUTH-002.
- **Paths:** backend/devices/models.py; backend/devices/migrations/; backend/devices/tests/test_migrations.py.
- **Work:** Retain Django's existing user model and staff flags/groups. Add CustomerMembership with a unique user relation and protected Customer foreign key: one organization per customer account, many accounts per organization. Use membership as the customer-role marker; customer users have neither staff nor superuser flags nor staff groups. Centralize eligibility checks and reject mixed identities. Do not infer membership from contact email, username, or device serial. Review existing database data before applying additive migrations; do not reset databases, replace AUTH_USER_MODEL, or alter historical migrations. Archiving an organization denies portal access but does not revoke device credentials or interrupt devices.
- **Acceptance:** Fresh PostgreSQL migrations and upgrade from the existing schema preserve users, roles, customers, devices and audit history. One user cannot have two memberships. Multiple accounts may share one organization. Missing membership and mixed staff/customer identities fail closed. No existing staff user is converted or linked automatically.
- **Verification:** PostgreSQL migration/constraint tests and makemigrations --check; review upgrade and rollback procedure against a disposable copy.

#### CUST-002 — Extend secure browser authentication to customer sessions

- **Depends on:** CUST-001, AUTH-001.
- **Paths:** backend/devices/views.py; backend/devices/permissions.py; backend/devices/throttling.py; backend/config/urls.py; backend/devices/tests/test_staff_auth.py.
- **Work:** Extend existing /api/v1/auth/login/, session/ and logout/ browser contracts to return an explicit customer role and safe organization identity while preserving staff responses. Reuse HttpOnly/SameSite/Secure production cookie sessions, CSRF, key rotation, configurable expiry and the existing PostgreSQL login limiter; no localStorage bearer tokens or parallel unthrottled login. Evaluate current membership, organization archive status, account activity and role eligibility on every protected request. Preserve IsStaffUser and IsSuperAdministrator; customer login must not grant staff flags. Audit customer authentication without secrets and clear browser state on logout/expiry or access change.
- **Acceptance:** Valid customers log in, restore their session and log out with server revocation. Wrong/ambiguous credentials, inactive users, archived organizations, missing membership and conflicting roles receive generic denial. Expired, deactivated or membership-revoked sessions cannot read protected data. CSRF, session rotation, rate limits and secret-free audits pass. Customer sessions cannot use staff/admin or device-authenticated routes; existing staff login and permissions remain valid.
- **Verification:** Focused PostgreSQL authentication/CSRF/rate-limit tests plus staff authentication and permission regression tests.

#### CUST-003 — Provision and deactivate customer accounts through administrator UI and API

- **Depends on:** CUST-002, DATA-001, UI-001.
- **Paths:** backend/devices/serializers.py; backend/devices/views.py; backend/devices/admin.py; backend/config/urls.py; src/StaffUsers.jsx; src/LiveConsole.jsx; src/api.js.
- **Work:** Add super-administrator-only customer-user management under /api/v1/customer-users/ and the application user-management area. Create an account with email, validated initial password and an explicit active Customer assignment; list accounts and deactivate/reactivate them through controlled fields. Keep staff-user provisioning separate and unchanged. Validate normalized email uniqueness across eligible browser accounts, preventing ambiguity with existing case-insensitive duplicate records without destructive cleanup. Reject caller-supplied privilege/group fields and unauthorized organization or role changes. Commit account, membership and secret-free audit atomically, including native admin if exposed. No public registration, invitation email, automatic password delivery, customer self-editing or cross-organization reassignment UI.
- **Acceptance:** A super administrator creates a customer account that can sign in and sees only the assigned organization; deactivation removes access from an existing session on the next request. Support, customer, anonymous and device identities cannot list/provision/deactivate accounts or assign roles. Duplicate/ambiguous email, weak password, missing/archived organization and privilege injection fail safely. Passwords and hashes never appear in responses/audits. Staff creation continues to work.
- **Verification:** Provisioning/denial/audit-rollback API tests and administrator browser creation/deactivation flows, including accessible form errors.

#### CUST-004 — Expose read-only tenant-scoped customer device APIs

- **Depends on:** CUST-002, DATA-001.
- **Paths:** backend/devices/views.py; backend/devices/serializers.py; backend/devices/inventory.py; backend/config/urls.py; backend/devices/tests/test_inventory.py.
- **Work:** Add GET /api/v1/customer/devices/, /devices/{id}/ and /summary/ in the customer namespace. Resolve organization exclusively from the authenticated user's current membership. Scope querysets before lookups, search, filtering, pagination and aggregates; deny other methods. Allowlist only id, serial_number, model_name, software_version, location, last_seen_at and estimated online status; summary exposes only that organization's device/online/offline counts, generated_at and online_window_minutes. Exclude archived devices. Return a consistent 404 for absent or foreign device IDs and reject unsupported scope/filter parameters. Do not reuse unrestricted staff serializers or expose credentials, site contact details, internal notes, raw payloads, events/fault history, release/assignment metadata or audit records. Apply current organization ownership on every request and prevent cross-tenant caching.
- **Acceptance:** Customer A cannot obtain Customer B's records or counts through lists, details, direct URLs, serial search, filters, pagination or summary. Missing/inactive/archived membership fails closed. Reassignment removes A's access on subsequent requests and grants only the new owner's scope. Read-only methods and safe fields are enforced server-side. Threshold boundary, stale/never-connected status and zero-device counts are correct; staff APIs and device ingestion remain unchanged.
- **Verification:** Two-organization PostgreSQL API tests for field allowlists, filters/IDOR, aggregate isolation, reassignment, archive policy, prohibited methods and configured online-window boundaries.

#### CUST-005 — Integrate dedicated Persian RTL customer panel with live APIs

- **Depends on:** CUST-003, CUST-004, UI-001.
- **Paths:** prototype/onboarding/index.html (design reference only); src/LiveConsole.jsx; src/api.js; src/locale.js; src/live.css; src/Dialog.jsx.
- **Work:** Reuse the connected console's session/client/design components. Dispatch the authenticated customer role to /customer/devices and /customer/devices/:id; support refresh/direct navigation using the existing frontend hosting strategy. Show organization identity, My devices, read-only details, estimated connection state, last successful communication and freshness, plus logout/theme controls. Preserve the prototype's Persian RTL layout, sidebar/drawer, device table/cards and detail style without its staff onboarding, connect-demo, update simulation or localStorage identity. Hide staff navigation and do not fetch staff endpoints for customer sessions. Clear records and pending responses on logout, expiry or ownership/access change; avoid stale detail data after a denial. Add loading, no devices, no matches, never-connected, stale, API-error, not-found and session-expiry states with keyboard/focus/mobile/theme behavior. Live mode has no demo fallback.
- **Acceptance:** Customer login and session restoration enter only the dedicated panel; device search/list/detail and counts use authorized backend data. Direct staff URLs do not reveal staff pages or data. Logout/expiry clears data. Connection copy states an estimate based on the configurable threshold and never offers a remote connect/control action. Both themes, Persian RTL/LTR identifiers, mobile drawer and accessible states pass. Staff workflows and explicitly labeled demo mode remain separate.
- **Verification:** Production frontend build, focused browser tests for routing/states/role-specific requests and manual desktop/mobile keyboard/theme review.

#### CUST-006 — Verify customer isolation and real-backend browser acceptance

- **Depends on:** CUST-005.
- **Paths:** backend/devices/tests/; tests/browser/; docs/frontend-verification.md.
- **Work:** Consolidate tests added alongside CUST-001 through CUST-005 into a regression gate. Use two organizations, multiple accounts and devices, including missing membership, inactive account, archived organization, never-connected device and reassignment scenarios. Exercise login/logout/expiry, account provisioning/deactivation, all staff/admin/device denials, serializer allowlists, search/filter/detail/pagination/aggregate isolation and queued response cleanup. Run an isolated real-backend browser flow; mocked browser tests alone are insufficient. Check secrets are absent from responses/audits and preserve staff permission, ingestion/idempotency and update safety behavior.
- **Acceptance:** Focused security tests, relevant full PostgreSQL regression suite, migration checks and frontend build pass. A real-backend customer login/list/detail/logout/expiry and administrator create/deactivate walkthrough passes on desktop/mobile. Cross-organization access and privilege escalation are denied even through direct requests. Record actual commands/results and clearly distinguish mocked tests from real-backend acceptance.
- **Verification:** Documented PostgreSQL suite, frontend build, browser suite and controlled real-backend acceptance; inspect diff for secrets, stubs and demo/live confusion.

#### CUST-007 — Document customer setup and complete customer-access handoff

- **Depends on:** CUST-006.
- **Paths:** README.md; backend/README.md; docs/local-setup.fa.md; docs/staff-permissions.md; docs/frontend-verification.md; docs/implementation-plan.md; .beads/plan-map.json.
- **Work:** Document migration/upgrade steps, administrator customer-account creation and organization assignment, deactivation, password handling, role boundaries, customer routes, read-only archive/reassignment policy, connection estimate and local PostgreSQL startup. Describe auth/CSRF/expiry configuration using existing safe examples and keep .env secrets private. Record delivered versus deferred scope and actual verification; refresh Beads snapshot and map. Do not claim provider HTTPS settings, production deployment or rollout signing are complete.
- **Acceptance:** A developer follows the documented local setup and a super administrator provisions a customer who can access only their organization's devices. Setup/permission/browser docs agree with implementation and tests. Known production prerequisites and excluded features are explicit; new capability is not marked delivered before CUST-006 passes. Existing plan references and completed issue history are preserved.
- **Verification:** Review documentation links and run documented local smoke steps against a disposable environment; verify Beads dependencies, plan map and exported snapshot consistency.

### Optional follow-on (only if product owner confirms)

- **OPT-001 — Add authorized filtered log/device export (S/M):** Product spec §8.6 says later MVP increment if operationally required; not on critical MVP path. If authorized, define formats/fields/retention and access logging before implementation.

### Explicitly deferred product work

- Expanded customer self-service (events/fault history, update notices/actions, profile editing), public registration, payment/licensing/suspension, STM32 firmware updates, approved test-sheet catalog and AI assistant remain out of Phase 1 per `product-spec.md` §§4 and 6. Limited customer login/device visibility is approved and tracked in the customer-access increment above.

## 7. Critical path and parallelizable work

### Critical path

`OPS-001` (if Beads is required for tracking) → `ENG-001` → `ENG-002` → `ENG-003` → `AUTH-001`/`AUTH-002` → `DATA-001` and `DEVICE-001` → `DEVICE-002` → UI integration slices → `REL-001` → `REL-002` → `OPS-003`/`OPS-004` → provider-specific `OPS-005` and staging acceptance `UI-005`.

`REL-003` is a separate safety critical path for **production update delivery**: it depends on `REL-001` plus device updater inspection and is a hard gate before real device rollout, even if all other MVP features are ready.

### Customer-access dependency path

Existing ENG-002/AUTH-002 → CUST-001 → CUST-002 → CUST-003 (account administration) and CUST-004 (read-only scoped APIs) → CUST-005 (customer UI) → CUST-006 (integrated security/browser acceptance) → CUST-007 (setup/handoff) → UI-005 final console acceptance. Existing AUTH-001, DATA-001 and UI-001 are additional dependencies as listed above. The existing release-signing production gate remains independent and unchanged.

### Safe parallel work after shared contracts

- After `ENG-001`/`ENG-002`/`ENG-003`, backend access/data work (`AUTH-001`, `DATA-001`, `DEVICE-001`) can split across contributors if model/API ownership is agreed.
- `UI-001` can proceed against documented API schemas while backend implementation proceeds; live integration (`UI-002`–`UI-004`) waits for stable auth and payload contracts.
- Device-event work (`DEVICE-002`) and customer/device UX can proceed in parallel after migrations and their API shape are agreed.
- Release signing research (`REL-003`) can proceed in parallel with release UI/API scaffolding; enablement cannot.
- CI (`OPS-002`) can be built while domain work proceeds, but require the initial test/config interfaces from `ENG-001` and `ENG-003`.

Shared contracts needed for parallelism: staff auth mode and CSRF/origin policy; role matrix; API schema and canonical enum values; pagination/error envelope; device event batch/partial-ack semantics; release status/target semantics; frontend runtime API origin.

## 8. Verification and release readiness

Verification is integrated into tasks, not deferred to a final hardening phase. Minimum milestone exits:

1. **Foundation:** Locked dependency install; clean PostgreSQL migrations; `makemigrations --check`; tests execute against PostgreSQL; Beads task state visible if initialized.
2. **Admin/auth slice:** Role matrix passes API tests; secure session/CSRF lifecycle verified; customer/device duplicate/archive/search flows pass.
3. **Device slice:** Credential rotation/revocation works; retry, conflicting IDs, mixed batches and out-of-order fault timelines pass PostgreSQL integration tests; device owner approves payload contract.
4. **UI slice:** Production frontend builds; login, list/detail/search, event history, status freshness and release views use live APIs; loading/empty/error/permission states are verified; Persian RTL and LTR codes remain readable at mobile/desktop widths.
5. **Customer slice:** All CUST-001–CUST-007 acceptance criteria pass: real customer login/logout/expiry and administrator provision/deactivate browser flows; two-organization list/detail/search/filter/pagination/aggregate isolation; missing membership and reassignment denial; prohibited mutations; correct threshold/never-connected/freshness states; no demo fallback and no staff regression.
6. **Container/staging:** Non-root production API container, health/readiness, explicit migration job, private database and durable storage work; no production secrets baked into image; CI passes.
7. **Production gate:** Provider/domain/TLS/secrets selected; backups and restore tested; SLO/retention/owner set; update signature verified with the actual device updater before any production package rollout; production smoke test and rollback rehearsal complete.

Use automated tests for data integrity, auth, authorization, event idempotency/races, release targeting, migration and container behavior. Manual checks remain necessary for browser accessibility/responsive UX, provider ingress/TLS, restore/rollback rehearsal and actual device updater safety. Do not treat a successful build as product acceptance.

## 9. Risks, open questions, and deferred scope

### Blockers for production or specific tasks

- **Production browser auth/deployment:** Provider origin/proxy arrangement must be known to finalize secure cookie, CSRF and CORS settings. Blocks production auth configuration, not UI design/API tests.
- **Production software rollout:** Device updater source/capability, signature protocol and key custody are unknown. Blocks `REL-003` and real update rollout; release CRUD and staging workflow can proceed.
- **Provider operations:** Provider and database service are not selected. Blocks provider-specific deployment (`OPS-005`), not portable Docker artifacts.
- **Capacity/recovery commitments:** Fleet/event scale, retention, SLO, RPO/RTO and owner are not defined. Blocks production readiness targets/alerts and sizing, not initial feature development.
- **Beads environment (updated 2026-11-15):** CLI and project configuration are initialized. Milestone tasks and dependencies are imported. Configuration, the ID mapping, and an issue snapshot are reviewable in Git; the embedded database and binary stay local. Shared remote sync and off-machine backup remain unconfigured. See [development workflow](development-workflow.md).

### Nonblocking uncertainties

- Mandatory customer contact/address fields beyond current model.
- Whether support users may receive update-publish permission beyond default read-only.
- Exact refresh cadence for dashboard status.
- Whether event export becomes an MVP operational need.
- Exact event time tie-break when timestamps match; recommend server receipt then immutable PK for deterministic ordering, after verifying product semantics.
- Frontend/package dependency lock strategy and supported browser matrix.

### Deferred

Expanded customer self-service beyond the approved device panel, public registration, license/payment enforcement, safe suspension policy, STM32 firmware updates, injector test-sheet data/approval, AI assistant, and event export unless explicitly promoted. These are not hidden dependencies for the approved MVP.

## 10. Original recommended starting point (historical)

Start with **ENG-001: Establish locked Python project tooling**, preceded by **OPS-001 Beads initialization** if the team expects all work to be tracked in Beads from the first implementation PR. ENG-001 is small enough to review independently and establishes the lock/config base needed for migrations, test tooling, and Docker builds without changing product behavior.

ENG-001 is complete when the backend's current runtime dependencies install from a committed `uv.lock` using documented Python 3.12 commands, the app passes a Django configuration check, and no parallel `requirements.txt` source of truth remains. Before ENG-002, inspect every target database and confirm whether migration baselining must preserve existing data. Then establish migrations and PostgreSQL tests before changing authentication or ingestion behavior.

## 11. Customer-access implementation handoff

The customer increment adds migration 0006_customer_membership, current-database browser-role helpers, audited administrator customer-account provisioning/deactivation, isolated read-only device APIs and summary, and Persian RTL customer list/detail routes with safe session/data cleanup. Existing staff and device API paths are retained. The explicit demo prototype remains separate. Beads CUST-001 through CUST-007 record the delivery and acceptance evidence; do not reopen completed staff tasks for this extension.

The existing application database and running service are not automatically upgraded by development or tests. Rebuild the API, apply the additive migration once and recreate the local API using the documented setup commands. Customer memberships are explicit; no existing account or organization contact email is converted. Static production hosting needs SPA fallback for /customer/devices and detail URLs.

See docs/frontend-verification.md and scripts/customer-browser-qa.mjs for reproducible real-backend acceptance using generated accounts and a disposable PostgreSQL database. Provider-specific HTTPS/cookie/proxy configuration, static hosting, backups/restore, operational targets and the signed-update production gate remain unchanged prerequisites. This increment does not deploy or enable production update rollout.

Verified 2026-11-18: 278 PostgreSQL tests, 15 mocked browser tests, and nine real-backend Edge acceptance checks passed. Frontend production build, whole-backend Ruff, Django system check, migration drift check and diff whitespace check passed. The verification script removed its temporary QA database/services; the ordinary application database and running API were left unchanged.
