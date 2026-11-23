# Design Language | Pishgaman Shargh

## Experience Goal

The staff dashboard should help administrators and support staff understand fleet health and recent reports at a glance. The dedicated customer panel helps a customer inspect only their own organization’s assigned devices and estimated connectivity. The interface is Persian and right-to-left, following a “summary first, details when needed” pattern: essential data remains visible in cards and tables, while history, supporting information, and actions are available in expandable rows, accordions, detail panels, or dedicated pages. Frequent tasks such as searching by serial number and reviewing faults should be one action away.

## Visual Principles

- **Calm and precise:** Use the organization’s dark green for primary actions and healthy states. Use warm, low-contrast grays for surfaces and secondary text.
- **Considered density:** Keep enough whitespace between sections while making management table rows compact and easy to scan.
- **Progressive disclosure:** Keep titles and statuses visible. Move secondary details into tabs, accordions, detail panels, or dedicated pages.
- **Purposeful motion:** Use short, smooth transitions for tab changes, opening details, pagination, and successful-action feedback. Motion must not be decorative or block interaction, and `prefers-reduced-motion` must be respected.
- **Trustworthy feedback:** Show error, offline, and installation states with clear text and visual cues; never rely on color alone.

## Interface Tokens

| Token | Light value | Use |
|---|---|---|
| Canvas | `#F5F6F3` | Application background |
| Surface | `#FFFFFF` | Panels, cards, menus |
| Ink | `#25312D` | Primary text |
| Muted | `#89928C` | Secondary text |
| Accent | `#1D7457` | Primary action and selection |
| Success | `#267A55` | Online and successful states |
| Warning | `#B47732` | Warning state |
| Danger | `#C04D4C` | Active fault |
| Border | `#EBEEEA` | Subtle separation |

The dark theme should preserve the same semantic roles and readable contrast. Components should use semantic tokens instead of scattered hard-coded color values.

## Typography and Directionality

Use Vazirmatn as the primary typeface with system fallbacks. Display serial numbers, software versions, times, and fault codes left-to-right; keep labels and page structure right-to-left. Suggested sizes are 22–24 px for page headings, 13–15 px for panel headings, 10–13 px for interface text, and 9–10 px for metadata. In production, body text on mobile must meet WCAG readability expectations.

## Foundation Components

Prefer native elements and shared components wherever possible: `Button` (primary/secondary/quiet), `IconButton`, `Badge`, `Card`, `Input`, `Select`, `Tabs`, `Table`, `Avatar`, `Breadcrumb`, `Dialog`, `Toast`, `EmptyState`, and `Pagination`. Use 6–10 px corner radii, very subtle shadows, and a single icon family. A custom component is justified only when composing foundation components does not meet a genuine device-specific need.

## Responsive Design and Accessibility

- Start with mobile. Prioritize the page title and primary action, metrics, event list, then a horizontally scrollable device table or device cards.
- On small screens, turn the sidebar into a drawer with an obvious close action and backdrop.
- Provide touch targets of at least 40×40 px, visible focus states, accessible names, and meaningful disabled states.
- Convey connection, fault, and success states with both text labels and visual indicators.
- Keep interface updates responsive and non-blocking. With live data, use server-side pagination and progressively load event history.

## Product Voice

Keep copy concise, respectful, calm, and professional. Replace vague technical messages with a clear status or next step: “The device connection has been restored,” “Reports will sync after the device reconnects,” or “No devices found. Try changing your search.”

## Phase One Boundaries

The visual prototype uses sample data to establish the experience. The connected staff console is implemented separately; remaining delivery is tracked in Beads. Product requirements include authenticated API access and roles, customer and unique-serial registration, batch event ingestion with unique IDs to prevent duplicates, event and receipt timestamps, offline queue/sync support, customer management, software release and rollback workflows, and audit logging. The server must not participate in real-time test control. Device and event models should allow approved test sheets and an AI assistant in a later phase; generating test values without a reliable source is not allowed.

## Approved Customer Panel (2026-11-18)

This MVP extension is implemented in src/CustomerPanel.jsx and src/CustomerUsers.jsx and tracked by CUST-001 through CUST-007. prototype/onboarding/index.html remains the visual reference for layout, colors, typography, RTL navigation/drawer, device cards/table and read-only details. That historical prototype is a staff onboarding simulation, explicitly says customers cannot log in, and stores demo state locally. Its old scope copy does not override this approval. The live customer panel extends its visual language with real customer authorization and data; the prototype's connect/update simulation stays separate.

### Entry, navigation and routes

- Keep the shared email/password sign-in, generic credential error, password visibility control, pending state and accessible labels. There is no customer registration link or role selector that grants permissions.
- A successful customer session opens /customer/devices. A device opens /customer/devices/:id; back navigation returns to the list. Refresh and direct links restore and check the server session before rendering protected content. The client uses the existing application structure and browser history; static hosting must provide SPA fallback for these routes.
- Display safe organization identity, My devices, theme preference and logout in the familiar RTL shell. Support mobile drawer dismissal, keyboard focus and LTR identifiers. Do not show staff customers/users/events/releases/audit navigation, admin controls, connect actions or update actions to customers. Staff routes remain role-protected even when entered directly.
- Super administrators get a clearly labeled customer-account area in user management, distinct from staff accounts: select an active organization, enter identity/initial password, create account, and activate/deactivate an existing account. Show server field errors and creation status; never display stored passwords/hashes. Support/customers do not receive these controls.

### Customer device experience

- List only assigned non-archived devices, with serial, model, software version, estimated connection status and last communication. Details may also show installation location. Keep contacts, internal notes, events/faults, rollout information and credentials outside this scope.
- Search serial/model and filter connection state using scoped server queries and pagination. Optional summary cards contain only this organization's total/online/offline counts, never staff fleet metrics.
- Label connectivity as an estimate based on the last successful communication and configurable threshold (15 minutes by default). Show refresh/freshness time and a never-connected message when no communication exists. Do not imply a currently open channel, real-time certainty or permission to control tests.
- Preserve themes, responsive cards/table, Persian dates/numbers, LTR serial/version values, semantic status labels, visible focus, keyboard navigation, touch targets and reduced motion.

### State and data boundaries

| State | Required behavior |
|---|---|
| Session restoration/loading | Announce pending state; do not flash staff content or cached customer data |
| Empty organization fleet | Explain no assigned devices; no add-device action or invented sample records |
| Search has no matches | Offer clearing the search/filter; distinguish from zero assigned devices |
| Never connected | Explicit text and no invented last-seen time |
| Refresh/stale data | Show timestamp/basis and pending/error status; do not present stale values as current |
| API outage | Visible retry/error state, distinct from empty results; no demo fallback |
| Foreign/missing/reassigned device | Generic unavailable/not-found view; clear protected details after denial |
| Expired/deactivated/revoked session | Clear organization/device data and pending requests, return to sign-in with a calm explanation |
| Logout | End server session and clear protected data; browser back must not restore an authenticated view |

The backend permission matrix is authoritative. Hidden controls are presentation only. Keep prototype/localStorage demo data separate from the live customer panel; additional prototype features and customer self-service remain deferred.
