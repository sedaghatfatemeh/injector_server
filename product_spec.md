# Product Specification: Pishgaman Shargh Injector Device Management Platform

**Document status:** MVP product definition — decisions confirmed  
**Product owner:** Pishgaman Shargh  
**Primary users:** Internal administrators, support staff, and (in a later customer-access phase) customers  
**Related design document:** [`design-spec.md`](./design-spec.md)

## 1. Product Summary

Pishgaman Shargh manufactures injector testing equipment for heavy vehicles. Each sold device has an onboard computer and dedicated Python software that operates the test process. This product is an independent web application and server for registering sold devices, receiving their diagnostic and operational logs through an internet API, and helping authorized people manage the fleet.

The platform is a monitoring and management system. It does not control, modify, or interrupt a test in progress. Device-side software remains responsible for test execution, fault diagnosis, offline buffering, and safe update installation. When a device reconnects, its locally queued events are delivered to the server and become visible in the dashboard.

The first release is an internal MVP focused on authenticated staff access, customer and device records, event ingestion and review, connectivity visibility, and controlled Python software updates. Customers do not sign in during the MVP. Payment/license enforcement, STM32 firmware updates, and AI assistance are later-phase capabilities.

## 2. Problem and Opportunity

Today, device information and diagnostic history are distributed across devices and customer sites. Support staff need a reliable way to identify a device, understand its customer and software version, see when it last communicated, and review faults or update outcomes. Internet outages must not erase device logs or cause duplicate events when queued data is eventually delivered.

The platform creates a shared operational record while keeping device testing autonomous and safe.

## 3. Goals

1. Give authorized staff a secure, searchable view of registered customers and devices.
2. Receive, persist, and display device events, including delayed events sent after an outage.
3. Prevent duplicate event records when devices retry delivery.
4. Make online/offline status and last successful communication easy to understand.
5. Provide a clear event and fault history, including active and resolved status as reported by the device.
6. Provide a foundation for distributing compatible Python software updates and tracking installation results.
7. Deliver a fast, polished, mobile-first Persian experience with light and dark themes.
8. Keep the data model and service boundaries ready for future customer access, licensing, test sheets, and AI assistance.

## 4. Non-Goals and Safety Boundaries

- The server does not control a test, alter test parameters, actuate hardware, or issue time-critical commands.
- The server does not diagnose faults. Diagnosis and fault-state transitions are produced by device software; the server stores and presents the reported facts.
- No STM32/32-bit microcontroller firmware update is included. Phase-one update scope is the Python application only.
- The MVP does not implement payment collection, contract management, automatic license suspension, or remote disabling of a device.
- The MVP does not generate injector test-sheet values or provide AI advice.
- Dashboard connectivity status is an operational estimate based on communication timestamps, not proof that a device is executing a test safely.

## 5. Users and Roles

### 5.1 Super Administrator

An internal, fully trusted operator who can manage staff access, customers, devices, software releases, rollout targets, and audit history. Customer creation and staff account provisioning are restricted to this role in the MVP.

### 5.2 Support Staff

An internal user who can search and view customers/devices, review faults and event history, and inspect update status. By default, support staff cannot create administrator accounts, publish a software release, change security settings, or perform destructive actions. Update permissions can be granted explicitly if the operating policy requires them.

### 5.3 Customer User (Later Phase)

A customer may eventually sign in and view only their own organization’s devices, logs, and update notices. Customer self-service is not part of the initial MVP. The data model and authorization model must be tenant-aware from the beginning so adding customer accounts does not require redesigning ownership boundaries.

## 6. Product Scope by Phase

### Phase 1: MVP (Confirmed)

- Secure email/password sign-in and sign-out for internal administrators and support staff. Staff accounts are provisioned by an administrator; there is no public registration.
- Role-based authorization and audit records for sensitive actions.
- Customer registration and management by the super administrator.
- Device registration with a globally unique serial number and customer assignment.
- Device inventory, search, filtering, connectivity/last-seen display, and device detail view.
- Authenticated API for device check-in and event batch ingestion.
- Persistent event history with duplicate protection and active/resolved status as reported by devices.
- Dashboard overview with fleet metrics, recent events, and active faults.
- Python application release registry with an externally hosted package URL, compatibility metadata, package SHA-256 digest, automatic publication after an authorized release record is created for all compatible devices or an explicit selected-device set, install outcomes, and retained previous release metadata. The device downloads from the external HTTPS host and installs only while idle and safe.
- Persian (Farsi), RTL initial interface, with localization-ready messages and date/number formatting architecture.
- Django application/API with PostgreSQL as the production relational database.
- A device is online if its last successful authenticated check-in was within the previous 15 minutes; this threshold is configurable.
- Light and dark themes, responsive layouts, accessible controls, and clear loading/empty/error states.

### Phase 2: Customer Access and License Operations

- Customer accounts restricted to their own organization and devices.
- License state, payment due dates, reminders, suspension, and reactivation workflow where contractually applicable.
- Suspension requires an authorized, authenticated action, records a reason and audit event, and must never abruptly stop a running test or pressure process. The device applies any restriction only at a safe point under an explicitly defined offline and grace-period policy.

### Future Expansion: Test Sheets and AI Assistant

- Approved test-sheet catalog indexed by injector brand, model, and part number, with parameters such as RPM, pressure, delay, pulse width (PW), and expected fuel output.
- Store source, approval status, revision, and provenance for every test sheet.
- AI assistant grounded only in approved test sheets, the device manual, and authorized device/event records.
- The assistant must cite the source used, distinguish missing evidence from known facts, and refuse to invent test-sheet values. AI is not part of Phase 1.

## 7. Core User Journeys

### 7.1 Staff Sign-In

1. User opens the application and enters credentials.
2. The server authenticates the account and returns a secure session.
3. The user sees only navigation and actions allowed by their role.
4. Sign-out ends the server session. Inactivity/session expiry follows a configurable security policy.

### 7.2 Register a Customer and Device

1. Super administrator creates a customer with organization name and contact details.
2. Super administrator registers a device with a unique serial number, model, assigned customer, and optional deployment details.
3. The server rejects a duplicate serial number and explains how to resolve it.
4. Device details become searchable and ready for API identity provisioning.

### 7.3 Review Device Health and History

1. Staff searches by serial number, customer, or model and may filter by connection state or active faults.
2. The device list shows model, customer, software version, last communication, connection state, and active fault count.
3. Selecting a device opens a detail view with contact details, event/fault history, software history, and update results.
4. Detailed history is progressively disclosed (for example, accordions or tabs) so common workflows remain quick to scan.

### 7.4 Deliver and Review Device Events

1. Device software records an event locally with a stable unique event ID and original occurrence timestamp. Fault lifecycle updates also carry a stable fault ID shared by the active and resolved event records.
2. If offline, the device retains the event in a durable local queue and continues its independent local operation.
3. On reconnection, the device retries delivery until the server acknowledges the event batch.
4. The server authenticates the device, validates the batch, stores each event idempotently, and acknowledges accepted or previously accepted IDs.
5. The dashboard shows occurrence time and server receipt time where useful, making delayed delivery understandable.
6. A repeated event ID for the same device never creates another event record. Conflicting reuse of an ID is rejected and logged.

### 7.5 Publish a Python Software Update

1. A super administrator creates a release record with version, external HTTPS package URL, SHA-256 digest, supported models/current-version constraints, and release notes.
2. The release is published automatically to either all active compatible devices or the explicitly selected compatible devices.
3. The device checks in with its serial number, current application version, and safe/idle state. The server returns update metadata only when a newer compatible release is available.
4. The device downloads the package directly from the external HTTPS host, verifies it against the manifest digest and trusted release metadata, and installs only while idle and safe.
5. The device reports downloaded, installed, failed, or rolled-back status and diagnostic details that do not expose secrets.
6. Staff can inspect rollout progress and retain access to prior known-good releases. Rollback is initiated through a deliberate, audited release action and applied by the device at a safe point.

## 8. Functional Requirements

### 8.1 Authentication and Authorization

- All dashboard pages and administrative APIs require authentication, except explicitly public sign-in and health endpoints.
- Enforce role-based access on the server; hiding a button in the UI is not an authorization control.
- Support super administrator and support staff roles in Phase 1.
- Store passwords using a modern, slow password hash; do not store or log plaintext passwords.
- Use secure session handling (Secure, HttpOnly, and appropriate SameSite cookies when cookie sessions are used), CSRF protection where applicable, rate limits on sign-in, and session revocation.
- Record actor, action, target, time, and outcome for security-sensitive changes.
- Customer access in a future phase must enforce organization-level data isolation in every API query.

### 8.2 Customer Management

- Create, view, update, and archive customer records (archive rather than destructive deletion when records are referenced).
- Store organization name, primary contact name, phone, email, address/region, notes, and record timestamps as applicable.
- Validate required fields and normalize searchable phone/email fields.
- Provide a customer detail view with assigned devices and relevant contact information.

### 8.3 Device Management

- Store unique serial number, model, customer, software name/version, registration date, last check-in, derived connection state, and deployment/contact metadata as applicable.
- Reject duplicate serial numbers with a clear message.
- Allow authorized staff to add, edit, view, and archive devices; customer assignment changes must be audited.
- Search by serial number, customer, and model. Filter by connection state, model, customer, and active-fault presence.
- Show a device’s connectivity and last-seen time with an explicit “last updated” basis. The online timeout must be configurable and visible in operational documentation.
- Keep a historical record of software versions and reported update results.

### 8.4 Device Identity and API Ingestion

- Each device must authenticate using a unique revocable credential provisioned for that device. Do not trust a serial number supplied without authentication.
- Provide versioned API endpoints for device check-in and event batch submission.
- Validate payload size, schema, timestamps, identifiers, event types, and device authorization.
- Apply rate limits and protect ingestion from replay or abuse. Transport must use TLS.
- Support retryable batch delivery and idempotent event creation. Return per-event accepted/duplicate/rejected outcomes so devices can safely retry.
- Store both event occurrence time and server receipt time in UTC; render in the user’s configured locale/timezone.
- Ingestion must be resilient to delayed, out-of-order batches. A late-arriving event retains its original occurrence time and does not overwrite a newer device check-in.
- Define retention and export policies for logs before production rollout.

### 8.5 Events, Logs, and Faults

- Store, at minimum: event ID, optional stable fault ID, device ID, event type/code, human-readable summary or translation key, event occurrence time, server receipt time, reported state, software version, and optional structured metadata.
- Support fault states reported by the device, including active and resolved. A lifecycle change has a new event ID and the same fault ID; the server shows the newest state by occurrence time and does not infer or change it. Delayed older events remain in history without replacing the latest state.
- Display active faults and recent events on the overview and full chronological history on the device page.
- Allow filtering by device, customer, event code/type, state, and time range; support pagination and a useful empty state.
- Clearly distinguish event time from upload/receipt time when an event was buffered offline.
- Avoid exposing credentials, personal secrets, or unnecessary raw payload fields in logs and UI.

### 8.6 Dashboard and Reporting

- Show fleet totals, online/offline counts, active fault count, and recent event volume with the data freshness timestamp.
- Provide a searchable device inventory and a recent event feed.
- Provide device and fault detail without forcing users through unrelated pages.
- Support exporting authorized, filtered device/event data in a documented format in a later MVP increment if operationally required; exports must respect the caller’s authorization.
- Never present stale cached status as current; indicate loading, last refresh, and stale-data conditions.

### 8.7 Python Software Updates

- Keep a release registry with version, externally hosted HTTPS package URL, SHA-256 digest, compatibility rules, release notes, creating actor, publication time, and status (published or withdrawn).
- An authorized super administrator creates the release record and selects either all devices or explicit devices; it becomes published automatically to that target, subject to compatible model rules. Newly registered compatible devices can discover the current release only when the release targeted all devices.
- Expose a device-authenticated update manifest endpoint. The manifest returns version, external package URL, digest, and release notes. The device downloads the package directly from the external host; the application server does not proxy or store the package.
- Verify package integrity on the device against the manifest digest. Publisher authenticity must additionally use signed release metadata or an equivalent mechanism; a digest alone is not publisher authentication.
- Device must report its current version and safe/idle eligibility. The server may offer an update, but the device makes and enforces the final safe-install decision.
- Record per-device update lifecycle: available, downloading, downloaded, installing, succeeded, failed, or rolled back, plus reported timestamps and a sanitized result code.
- Keep previous release metadata and allow an authorized administrator to withdraw a release. A super administrator may reassign a retained older release to specifically selected devices with an audited reason; the device applies the rollback only at a safe point and never during a running test.
- Phase 1 covers Python application packages only; STM32 firmware is explicitly excluded.

### 8.8 Localization, Theme, and UX

- Phase 1 interface language is Persian (Farsi), RTL. Architecture must externalize user-facing strings and support locale-specific dates, numbers, and directionality so a second language can be added without rewriting screens.
- Provide light and dark themes and remember the user’s preference.
- Follow the companion `design-spec.md` for visual tokens, typography, component reuse, progressive disclosure, and motion.
- Prefer established design-system components and native controls; custom components require a clear product need.
- Use compact transitions between meaningful states. Respect reduced-motion preferences and keep animations short, non-blocking, and performant.
- Provide keyboard navigation, visible focus, semantic labels, sufficient contrast, responsive touch targets, and screen-reader announcements for asynchronous status changes.
- Use calm, kind, professional copy. State what happened and, where useful, what the user can do next.

## 9. Core Data Entities

- **User:** identity, credential hash/provider reference, role, status, last sign-in, audit timestamps.
- **Customer:** organization profile, contacts, status, timestamps.
- **Device:** unique serial, model, customer reference, device credential reference/status, application version, last check-in, deployment metadata, status.
- **Device Event:** stable event ID, device reference, type/code, occurrence and receipt timestamps, reported state, software version, structured payload, deduplication key.
- **Software Release:** version, package location, digest/signature, compatibility criteria, release notes, status, publisher and timestamps.
- **Update Assignment:** release, target device/group, rollout state, lifecycle timestamps, device-reported result.
- **Audit Entry:** actor, action, target, timestamp, outcome, request/source context with secrets excluded.

Future entities should include **License** and **Approved Test Sheet** without coupling either to real-time test control.

## 10. Non-Functional Requirements

### Security and Privacy

- Encrypt network traffic with TLS and protect sensitive stored data using managed encryption at rest where available.
- Keep device credentials, signing keys, and secrets in a managed secret store; support rotation and revocation.
- Apply least privilege, input validation, output encoding, secure upload handling, and dependency/security maintenance.
- Audit administrative and release actions without writing secrets or full sensitive payloads to audit logs.
- Define backups, recovery objectives, retention, deletion, and data export controls before production launch.

### Reliability and Offline Operation

- Device software is the source of truth for its local queue. It must persist events across process restarts and power loss, retry with bounded backoff, and remove acknowledged events only after server confirmation.
- Ingestion is idempotent and accepts delayed/out-of-order events.
- A server outage or internet interruption must not block or terminate local tests. The device continues local operation and synchronizes later according to its own safe design.
- The dashboard communicates last contact and stale status instead of implying real-time certainty.

### Performance and Scalability

- Common dashboard interactions should feel immediate on representative desktop and mobile hardware.
- Use indexed lookups for serial number, customer, occurrence time, and event code; paginate large event histories on the server.
- Avoid loading unbounded logs or rendering large event collections in one page.
- Define measurable service targets (availability, ingestion latency, dashboard response time, and recovery point/time) before production deployment based on fleet size and operating needs.

### Maintainability and Extensibility

- Separate dashboard, identity/authorization, device ingestion, event storage, and release/update responsibilities behind documented interfaces.
- Version external APIs and validate schemas so device software can evolve without breaking older deployed units.
- Externalize interface strings and use stable event codes for future localization and AI retrieval.
- Keep AI and test-sheet modules optional and isolated; their absence must not affect core device monitoring.

## 11. Key Acceptance Criteria for MVP

1. An unauthenticated user cannot access dashboard or administrative data.
2. A super administrator can create a customer and register a device with a unique serial; a duplicate serial is rejected.
3. A support user can search by full or partial serial/customer/model and open the matching device detail.
4. Device check-in updates last-seen time and reported software version for the authenticated device.
5. A valid event batch is stored and visible with its device, event code/state, original occurrence time, and server receipt time.
6. Resending an already accepted event ID creates no duplicate; the device receives an acknowledgement that allows its local queue to advance.
7. Events uploaded after an outage appear with their original event time and are identifiable as delayed when receipt time differs materially.
8. Fault states are displayed as reported by the device and are not modified by server-side diagnosis.
9. Users can identify online/offline status, active faults, and update outcomes from the inventory/detail views.
10. Only a super administrator can create a release record; the record specifies all devices or selected devices and publishes automatically. The device verifies package integrity and defers installation while testing is active.
11. The interface works at mobile and desktop widths, supports both themes, respects reduced-motion settings, and remains keyboard operable.
12. Administrative changes and update lifecycle transitions are auditable without exposing secrets.

## 12. Open Product Decisions

The following implementation details remain open and should be resolved before production rollout. They do not block the initial API and data-model work:

- Which production hosting environment and external package hosting provider are approved?
- What is the expected installed-device count, event volume per device, and retention period?
- Which installation-contact fields beyond location are mandatory?
- What signing/integrity mechanism does the currently deployed Python device software support? Review the device client source or existing update protocol before finalizing publisher-signature verification.
- Are external package URLs stable or short-lived signed links? The package host itself will be selected later.
- What rollback approval is required?
- Should logs be downloadable/exportable in the MVP, and what fields may be included?
- What are the production targets for availability, ingestion response time, backup, and recovery?
- When should customer portal access and the second UI language be introduced?

## 13. Product Success Measures

- Share of registered devices that successfully check in within the configured interval.
- Time from a device event occurring to its availability in the dashboard, split by connected and delayed/offline delivery.
- Duplicate event rate (target: zero visible duplicate records for retried event IDs).
- Median time for support staff to find a device and understand its latest state.
- Update success/failure/rollback rates by release and device model.
- Authentication and authorization incidents, plus completion of periodic access reviews.

## 14. Assumptions

- Device-side Python software can be updated to persist a durable event queue, generate stable event IDs, authenticate to the API, retry safely, and report update state.
- Devices can report a safe/idle state, but the device—not the server—decides whether installation is safe.
- Initial dashboard users are internal staff; customer access is deferred while tenant boundaries are included in the architecture.
- The dashboard may show sample data during visual prototyping, but production must clearly separate sample/demo data from live device data.
- Product-specific retention, uptime, and scale targets remain to be agreed before production launch.

## 15. Confirmed Implementation Decisions

- **MVP scope:** Customer registration, device/log ingestion and review, and Python software updates are all in Phase 1.
- **Users:** Internal super administrators and support staff only. Customers do not have accounts in Phase 1.
- **Authentication:** Email and password; staff account creation is administrator-controlled.
- **Languages:** Persian (Farsi) and RTL for the initial UI; externalized strings and locale-aware presentation prepare for a second language.
- **Backend:** Python with Django.
- **Database:** PostgreSQL.
- **Online threshold:** A device is online if its last successful check-in is within 15 minutes; make the threshold configurable.
- **Customer minimum fields:** Organization name and responsible contact details.
- **Device record:** Serial number, model, customer, software version, and installation contact/location details.
- **Offline event delivery:** Stable unique ID per event, batch delivery, retry until server acknowledgment, and idempotent server acceptance.
- **Device API identity:** A unique revocable credential per device; credentials are provisioned out of band and stored as hashes server-side.
- **Fault lifecycle:** Each fault-state update is a separate immutable event with a new `event_id` and a shared stable `fault_id` connecting active/resolved updates.
- **Updates:** The application server stores version/link/metadata only; package files remain on an external HTTPS host. Creating a release record publishes it automatically to all compatible devices by default; the administrator may limit the target by model or specific devices/serials. Devices fetch packages directly and report lifecycle outcomes.
- **Update links:** The package hosting provider will be selected later; the release API currently accepts a full HTTPS package URL.
- **Release authenticity:** Review the current device updater before choosing a package-signing mechanism. SHA-256 is recorded, but by itself does not authenticate the publisher.
- **Reports:** Search, filtering, and detail views are included; file export is deferred.
- **Frontend integration:** The current dashboard remains a visual prototype using sample data while the real backend/API is implemented.
- **External hosting:** The package host is not selected yet; release records accept an HTTPS URL so the host can be chosen later.
- **Update signing:** Existing device updater capabilities need review before deciding the production signing protocol. The current API records a SHA-256 digest but does not yet provide publisher-signature verification.
- **Requested build outcome:** Implement a working backend and API, not only a product document or a sample-data UI.
