# User cards, profiles and email (TASK-036)

Implemented API: [TASK-036](../architecture/api.md#task-036-current).
Permissions: [administration matrix](../architecture/administration-access.md).

## User experience and authorization

Users directory names open `/users/:userId`; Profile links to the current user's card.
Cards and separately paginated organization/project lists require a normal authenticated
session. Anonymous/blocked/revoked sessions receive 401; temporary-password sessions receive
403. Blocked targets remain viewable. Cards contain names, active state, creation date and
capabilities, never another user's email or credentials. All active membership names are
intentionally disclosed, even outside the visitor's scope; `can_open` uses existing resource
read predicates. This never changes resource access. Archived/revoked memberships and those
with inactive parents/users are hidden. Both membership lists support loading additional pages.

Self profile changes use `/users/me/profile`; system administrators use the target UUID route.
Managers cannot edit others. Both name fields commit with one `profile_updated` audit event;
unchanged fields/no-op are omitted. Profile schemas forbid extra fields (including email/roles).
Audit viewing is still TASK-037, and `view_audit` remains false.

## Email workflow

Self requests require a normal session, a different valid email and a non-admin account.
An accepted request expires after six hours and replaces the previous request. No email is
reserved by a pending request. Occupied addresses return 409 both at request and confirmation;
unchanged self addresses return 422. The old email works until successful confirmation.

The link contains `#email-change=<credential>`. The SPA removes the fragment on opening and
keeps the token only in component memory; no browser storage or query/mutation cache contains
it. Opening a link performs no mutation. Sign in to the requesting account and explicitly
press **Confirm new email**. Wrong owner, malformed, expired, replaced or reused credentials
return 422. Reloading after fragment removal requires reopening the original email link.
A temporary-password session must first complete the password change; that cancels the request.

System administrators can change another user's email directly, including blocked users,
without unblocking them or changing their password. Direct changes cancel pending confirmation,
including a same-address direct no-op. The current system administrator's email cannot be
changed by any UI/API route, including self confirmation; use ADMIN_EMAIL/bootstrap.
Bootstrap selects the configured account rather than renaming the old administrator.

Email updates preserve UUIDs and sessions. Block, administrative password reset, self password
change and bootstrap role/credential changes cancel outstanding email actions through session
revocation. Email changes are excluded from both administrative audit and security metadata.

## Persistence, SMTP and release

Migration `0025_email_change` follows `0024_archive_lifecycle`. It adds one outbox/confirmation
row per user (PK/FK with ON DELETE CASCADE), a new unique random request UUID on replacement,
normalized email, token hash, expiry and retry state. Raw credentials are never stored.
The worker derives a purpose-separated HMAC credential from request UUID and signing key.
The existing lifecycle advisory lock and ordered user locks serialize requests, confirmations,
direct changes, reset/block/bootstrap. The users.email unique constraint is the final safeguard.
Profile/audit and email/request consumption each commit atomically.

Configure SMTP using [authentication operations](authentication.md#current-smtp-email-changes-only).
The existing `registration-mail-worker` entrypoint serves only email changes and expiry cleanup;
registration and password reset remain disabled. API/worker must share AUTH_SECRET_KEY and
PUBLIC_APP_URL. SMTP happens in a thread pool, with bounded socket timeout, under a shared
lifecycle lock and `FOR UPDATE SKIP LOCKED` row selection. Lifecycle changes may wait for a
current send. Failure retries after 10/20/40/80/160/300 seconds, bounded by expiry and polling;
only a sanitized outcome is logged. Delivery is at least once: a crash after SMTP acceptance
can resend the same link, but confirmation can succeed only once. No new runtime dependency.

Stop writers and deploy the migration, API, SPA and worker together. Shared deployments need
HTTPS as before. Downgrade to 0024 drops pending confirmations, not users/profiles/email/audit;
coordinate application rollback and request new links after upgrading. Never modify applied
migrations. Key rotation invalidates outstanding links; delete pending actions as part of the
existing coordinated credential-rotation procedure. No production/workspace database is migrated
by the tests.

Validation commands and coverage: [testing](testing.md#user-cards-and-email-task-036).
