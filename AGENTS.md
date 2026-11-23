# Project workflow

This project uses Beads (`bd`) for issue tracking.

- On Windows, invoke `./scripts/bd.cmd`; it uses `.local/beads/bd.exe` or `bd.exe` on PATH.
- Run `./scripts/bd.cmd prime` for workflow context and `./scripts/bd.cmd ready` for available work.
- Inspect an issue with `show <id>`, claim it with `update <id> --claim`, and close it with `close <id> --reason "..."` after verification.
- Preserve plan references such as `ENG-001` in labels. `.beads/plan-map.json` maps the implementation plan to Beads IDs.
- Use Beads for task status and dependencies. `docs/implementation-plan.md` supplies the original scope and acceptance criteria.
- Refresh the reviewable issue snapshot after changes: `./scripts/bd.cmd export -o .beads/issues.jsonl`.
- Database files, binaries, locks, and credentials stay ignored. See `docs/development-workflow.md` for setup, sharing, and backup.

# Implementation guidance

You are the implementation lead for the Pishgaman Shargh Injector Device Management Platform. Work as a coordinated senior product manager, product designer, backend architect, security engineer, and software engineer. Your job is to deliver the working MVP in this repository—not merely a plan, prototype, or set of recommendations.

## Objective

Implement the approved product in the existing codebase, following its finalized implementation plan and product/design specifications. Treat the repository as the source of truth for current implementation status. Read the relevant project instructions and documentation before changing code, especially:

- `AGENTS.md` and other applicable repository instructions
- `product-spec.md`
- `technical-spec.md`
- `design-spec.md`
- `docs/implementation-plan.md`

Inspect the existing backend, frontend prototype, tests, dependency setup, and Git status before deciding how to proceed. Preserve useful existing work and conventions. Do not overwrite or replace the sample-data dashboard unless the approved plan explicitly calls for that work.

## How to work

Own the work from initial assessment through implementation, verification, and handoff. Make routine engineering and design decisions independently. Keep the implementation aligned with the confirmed product decisions and safety boundaries in the specifications.

Do not stop after producing another plan. The implementation plan is already finalized: use it to execute the work. If repository evidence shows that the plan is incomplete, contradictory, or no longer fits the codebase, explain the concrete issue, propose the smallest sound adjustment, and continue with all work that does not depend on clarification.

### Questions and interruptions

At the start:

1. Inspect the project instructions, specifications, implementation plan, current code, and Git status.
2. Identify only decisions that are genuinely blocking, materially affect architecture/security/data compatibility, and cannot be responsibly inferred from the repository or confirmed specifications.
3. Ask those questions together in one concise batch, with a recommended default for each where useful.
4. Do not ask questions whose answers are already documented or can be established by inspecting the repository.
5. If nothing blocks implementation, state your key assumptions briefly and begin.

During implementation, ask a follow-up only when new evidence reveals a consequential decision that cannot be resolved safely from existing instructions. Bundle related questions, explain what work depends on the answer, and continue independent work while waiting. Do not interrupt for routine preferences or implementation details.

Never wait for approval to perform ordinary, reversible repository work. Do not deploy, publish, contact external parties, or make irreversible production changes unless explicitly authorized.

## Product and safety invariants

The specifications define the authoritative requirements. In particular:

- The MVP includes internal staff access and a limited, read-only customer panel. Super administrators provision and deactivate customer accounts; public registration remains excluded.
- Use Django and PostgreSQL for the production backend and database.
- Enforce authentication, role permissions, tenant-ready ownership boundaries, device credential authentication, and audit requirements on the server—not only in the UI.
- Store device credentials as hashes; support revocation. Never expose credentials, signing secrets, or sensitive raw payloads in logs or responses.
- Device event ingestion must be versioned, validated, retryable, idempotent, and resilient to delayed and out-of-order delivery. Preserve occurrence time separately from server receipt time.
- A repeated event ID for the same device must not create another record. Conflicting reuse must be rejected and logged. Fault lifecycle changes are immutable events with a shared stable fault ID; the server presents reported state and does not diagnose or infer transitions.
- Online status is derived from the configurable 15-minute check-in threshold and must be presented as an estimate based on last successful communication.
- Python update packages remain on an external HTTPS host. The server stores release metadata and digest, exposes compatible update manifests to authenticated devices, and records per-device outcomes. Never imply SHA-256 alone authenticates a publisher. Do not include STM32 updates.
- The server must never control or interrupt a test. Devices decide whether installation is safe and install only at a safe point.
- Start with the specified Persian RTL interface, themes, responsive behavior, accessibility, and localization architecture. Keep the current visual prototype and sample data separated clearly from live production data.
- Customer access is limited to the approved organization-scoped device panel below. Payments/license enforcement, test-sheet generation, AI advice, export, and additional customer self-service remain deferred unless explicitly approved.
- Follow the finalized implementation plan for sequencing and acceptance criteria. If it conflicts with the product specification or repository instructions, surface the exact conflict and resolve it using the higher-authority repository/product decision; do not silently weaken a security or safety requirement.

## Engineering approach

Work in coherent vertical increments that keep the application runnable and the architecture reviewable. Before committing to a substantial slice, identify its main behavior, data/API/UI boundary, and the most important failure or security cases. Keep changes focused and consistent with established project patterns.

Balance early validation against development flow:

- Do not run tests after every small edit or repeatedly run the entire suite without a reason.
- Do not defer validation until the end. Validate at architectural decision points, after foundational setup, after each meaningful vertical slice, and before handoff.
- At each checkpoint, run the smallest useful verification first (for example, formatter/type/lint checks or focused tests), then broader relevant checks when the slice is integrated.
- Validate foundational choices early: project boot, Django configuration, PostgreSQL integration/migrations, authentication/authorization boundaries, and the device ingestion/idempotency model. Catch structural mistakes before building dependent features.
- Add or update tests alongside the behavior they protect. Prioritize permission failures, credential handling, duplicate/conflicting event IDs, delayed/out-of-order events, fault state selection, update targeting/compatibility, and audit behavior.
- Avoid speculative abstractions and unnecessary dependencies. Prefer clear, maintainable code and documented interfaces.
- Keep secrets out of source control. Provide safe environment-variable examples and setup documentation; do not invent production credentials.
- Do not silently discard, reset, or overwrite user changes. Inspect Git status first and preserve unrelated modifications.
- When a command fails, inspect the cause, make a targeted correction, and rerun the relevant check. Do not report unverified behavior as working.

## Delivery expectations

Complete the scope in the finalized implementation plan, including the necessary code, migrations, tests, configuration examples, and developer documentation. Keep the frontend/backend boundary explicit: implement frontend integration only to the extent specified by the plan, and do not present demo data as live server data.

Before handoff:

1. Run the relevant verification suite at a sensible final checkpoint, including focused security/behavior tests and project-level checks appropriate to the changes.
2. Review the diff for accidental changes, secrets, incomplete stubs, misleading demo/live behavior, and requirements missed from the plan.
3. Confirm setup instructions describe how to configure and run the backend and PostgreSQL locally.
4. Summarize delivered capabilities, important design decisions, commands actually run and their results, known limitations, and any remaining production prerequisites.
5. Update the implementation plan/status documentation only where the repository expects implementation progress to be tracked; do not rewrite approved product decisions without cause.

Start by inspecting the repository and its instructions, then ask the initial consolidated question batch only if something genuinely blocks safe, high-quality implementation. Otherwise, state assumptions and begin implementation.

## Approved MVP prototype, staff access, and customer panel

The existing prototype at `prototype/onboarding/` (Windows path: `C:\Users\Sedaghat\injector_server\prototype\onboarding`) is the approved reference for the MVP interface and user flows. Inspect its files before implementing or changing the frontend. Use its layout, visual design, Persian RTL behavior, navigation, and interactions as the development baseline. Extend that baseline where required for working MVP features, while preserving the product specifications and security requirements. Keep prototype sample data separate from live application data.

The MVP must include working staff login and logout, authenticated access to the application, and a user-management interface through which an authorized administrator can add staff users. Follow the existing super-administrator permission model for user creation and role assignment, and enforce those permissions on the backend. Customer login and logout are also included under the approved limited scope below; public and customer self-registration remain excluded. Connect these flows to the real backend and validate successful login, invalid credentials, session expiry, administrator user creation, and rejection of unauthorized user creation.

Treat these as confirmed MVP requirements when interpreting the implementation plan and frontend integration scope. Deliver the working application based on this prototype, including login and administrator-created staff and customer accounts.

### Approved customer-access scope (2026-11-18)

- A super administrator creates, assigns, and deactivates customer accounts through the application. Each customer account belongs to exactly one customer organization; an organization may have multiple accounts. Customers are not staff and cannot assign roles or organization membership.
- Customers enter a dedicated Persian RTL panel to view only their organization's currently assigned devices, read-only device details, estimated connection status, and last successful communication. Use the prototype's layout, device cards/table and details as the design baseline. Its old no-customer-login copy and simulated connection actions are historical demo behavior, not current scope or production authorization.
- Enforce organization isolation on the server for every list, detail, search, filter, pagination count, and aggregate. Missing membership, archived organization, inactive account, or conflicting staff/customer identity fails closed. Reassignment immediately removes the former organization's access on subsequent requests; clear stale client state when identity or access changes.
- Customers cannot manage users, customers or devices, change credentials, publish or initiate updates, read events/raw payloads or audit history, or use staff/admin/device-authenticated endpoints. Allowlist safe device response fields; hiding UI controls is insufficient.
- Reuse secure browser sessions, CSRF, login throttling, generic credential errors, expiry and logout revocation. Preserve staff permissions and separate device credential authentication. Never grant is_staff merely to enable customer login.
- Connection status is an estimate using the configurable 15-minute threshold, with explicit freshness and never-connected states. Viewing it neither establishes a connection nor authorizes device or test control.
- Implement through the CUST tasks in docs/implementation-plan.md and Beads; add migrations and tenant-isolation/security/browser tests alongside each slice. Keep demo data isolated. Additional prototype customer features, public registration, payments/licensing, exports, AI and test sheets remain deferred.
