# Design Language | Pishgaman Shargh

## Experience Goal

The dashboard should help administrators and support staff understand fleet health and recent reports at a glance. The interface is Persian and right-to-left, following a “summary first, details when needed” pattern: essential data remains visible in cards and tables, while history, supporting information, and actions are available in expandable rows, accordions, detail panels, or dedicated pages. Frequent tasks such as searching by serial number and reviewing faults should be one action away.

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

The current dashboard uses sample data to establish the experience. A connected service still needs authenticated API access and roles, customer and unique-serial registration, batch event ingestion with unique IDs to prevent duplicates, event and receipt timestamps, offline queue/sync support, customer management, software release and rollback workflows, and audit logging. The server must not participate in real-time test control. Device and event models should allow approved test sheets and an AI assistant in a later phase; generating test values without a reliable source is not allowed.
