# Staff access and audit contract

The MVP has two internal roles. Both require an active Django user with `is_staff=true`. A super administrator additionally has `is_superuser=true`. Support requires membership in the `support` group and does not receive privileged writes. A bare staff flag, an arbitrary Django model permission, or a superuser flag on a non-staff account does not grant staff-console access. Customer access is a separate non-staff role with an organization-scoped read-only panel. Current eligibility helpers also deny any identity carrying both staff privileges and customer membership. See the [product permission matrix](../product-spec.md#54-mvp-permission-matrix) and [customer technical contract](../technical-spec.md#56-approved-customer-access-contract-2026-11-18). Customers must never receive staff flags or access to the staff operations below.

## Permission matrix

| Operation | Support | Super administrator |
| --- | --- | --- |
| Read dashboard, customers, device inventory/detail, event history, releases and update outcomes | Yes | Yes |
| Create/edit/archive customers and devices | No | Yes |
| Provision/rotate/revoke device credentials | No | Yes |
| Publish, withdraw or assign a retained release for rollback | No | Yes |
| List and create staff accounts in the console | No | Yes |
| List/create customer accounts and change their active status | No | Yes |
| Enter Django admin or inspect application audit records there | No | Yes |
| Modify operational facts through Django admin | No | No; use the audited API for supported operations |
| Create/edit/delete a stored device event or audit record | No | No |
| Submit device check-ins/events/update outcomes with a browser session | No | No; device authentication is separate |

Staff sessions can end their own session through logout. Expiry, account deactivation, password changes and removal of the staff flag prevent subsequent protected requests. Granting a support user Django model permissions does not broaden this business-role matrix. Optional support publishing permissions remain outside the default MVP policy until explicitly approved.

Customer sessions can inspect their own identity/organization, read their current organization's active-device list/details and scoped device/online/offline counts, and end their session. Organization is derived from CustomerMembership on each request, never a query parameter or browser claim. Missing membership, archived organization, inactive user or mixed identity fails closed. Reassignment removes the previous organization's device access on subsequent requests. Customers cannot list contact records, event/fault history, releases, updates or audits, mutate devices/accounts, or authenticate device API requests with a browser session. Account deactivation is checked on existing sessions as well as login.

Customer accounts are managed through the audited customer-user API/application area. Native UserAdmin excludes them, preventing that staff form from converting a customer into staff. Memberships are not editable through a native admin form. Customer provisioning rejects submitted role/flag/group fields, uses validated password hashing and a shared API username uniqueness boundary with staff provisioning, and commits user, membership and audit atomically. Customer contact email is never an implicit identity link.

## Auditing

Customer sign-in/out uses `customer.signed_in` / `customer.signed_out`. Invalid browser login remains a generic denial using the existing secret-free failure audit. Customer account provisioning and activation changes use `customer_user.created` and `customer_user.status_changed`; denied customer-account mutations use `authorization.denied`. Passwords, hashes, cookies, raw payloads and client-supplied privilege fields are excluded from audit details. Account changes roll back on audit failure.

Successful customer/device mutations, device credential changes, release actions and staff provisioning create application audit entries with actor, action, target, time and outcome. Denied customer/device/release writes use `authorization.denied`, a canonical numeric target ID when valid, and the server-selected operation name. Submitted request bodies, arbitrary path values, passwords and device credentials are not copied into denial audit details. User-directory denial events remain `staff.access_denied` / `staff.provision_denied`.

Native Django admin staff-account additions, changes and deletions also create `staff.created`, `staff.updated` and `staff.deleted` application audit entries. Details contain only the source, role/status flags and stable actor ID; password values and hashes are excluded. Django's native administrative log remains available. Account form writes and bulk account deletion commit with their audit entries; audit failure rolls the change back. These native account-change entries retain their `actor_user_id` detail even when the actor is later deleted and its foreign key becomes null.

The native admin login form accepts only active staff super administrators. Native admin and console login share the PostgreSQL-backed client-address rate limit, including its `Retry-After` response. Native admin sign-in successes/failures and sign-out are audited with source `django_admin`, so the administrative login is not a separate unthrottled sign-in path. Logout requires CSRF and its audit write; audit failure preserves the original session so the operator can retry. Native admin uses its Django username field; a console email session on the same hostname can access admin directly when authorized.

## Verification and deployment boundary

`backend/devices/tests/test_staff_permissions.py` exercises the role matrix, inactive and non-staff superusers, arbitrary Django permission grants, denial audit hygiene, native admin login/CSRF/rate limits, staff-account audit rollback, and immutable operational records. Run it with the documented PostgreSQL Pytest workflow in the [backend README](../backend/README.md).

Fourteen real Edge browser checks passed against an isolated database and temporary accounts: invalid and valid keyboard login, cookie flags/storage, refresh, user creation and dialog focus, support boundaries, native admin access and logout, console logout, server expiry, removal of staff status and mobile RTL flows. Local QA artifacts live under ignored `.local/browser-qa/artifacts/`; test databases and QA servers are removed after each run. User-facing console pages use live API data and do not fall back to demo records.

Production still requires the chosen HTTPS origin, trusted proxy chain and perimeter policy. Staff cookies must remain Secure/HttpOnly with CSRF enabled. The production admin should sit behind the operator access controls chosen for the hosting environment; these local/browser checks do not select a provider or publish the application.
