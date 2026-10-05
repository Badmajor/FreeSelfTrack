# Authentication operations (TASK-021)

> TASK-029 defines a future administrative release; it has not been implemented.
> The instructions below describe the current deployment. For the planned removal of
> registration/reset/deactivation and required ADMIN_* bootstrap, see the
> [migration plan](../architecture/administration-migration.md).

## Deployment and compatibility

Apply `uv run alembic upgrade head` and deploy API and frontend together. Migration
`0013_pending_registrations` adds pending signup and mail state; existing users and hashes are
unchanged. Start the new `registration-mail-worker` alongside the API. The standard Compose file
includes it. A downgrade to 0012 removes pending registrations; it preserves confirmed users.

Registration returns 202 with only a neutral message, for both new and existing addresses.
Clients must no longer expect a user object/201 or duplicate-email/409. The bundled frontend
shows “Check your email…” and offers an explicit confirmation form from the email link.
The form requires the password chosen for that registration, then directs the user to sign in.
If delivery is delayed or a link expires, submit registration again (subject to the same limits).
Do not activate requests you did not initiate. Existing accounts are never changed by confirmation.

## SMTP

Set these Compose variables in `.env` (examples are in `.env.example`):

| Variable | Meaning |
| --- | --- |
| `PUBLIC_APP_URL` | Public frontend URL; use HTTPS in shared deployments. Default `http://localhost:5173`. |
| `SMTP_HOST`, `SMTP_PORT` | SMTP server and port; default port 587. `localhost` inside the worker is the worker container. |
| `SMTP_SECURITY` | `starttls` (default), `tls` (usually port 465), or `plain` for an isolated local mail sink only. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Provider credentials, from environment; no credentials are printed. |
| `SMTP_SENDER` | Sender mailbox authorized by your SMTP server. |
| `AUTH_SECRET_KEY` | Same strong secret on API replicas and mail workers. Rotation invalidates outstanding links and access tokens. |

Both TLS modes verify certificates and hostnames. No opportunistic downgrade occurs.
For direct processes use the same names prefixed with `TRACKER_` (including
`TRACKER_AUTH_SECRET_KEY`). Start `uv run python -m app.workers.registration_mail` separately.
The worker polls every 5 seconds (`TRACKER_MAIL_WORKER_INTERVAL_SECONDS`), with a 10-second
SMTP socket timeout (`TRACKER_SMTP_TIMEOUT_SECONDS`, maximum 60). Retries wait 10, 20, 40,
80, 160, then 300 seconds until expiry. A failure after SMTP acceptance but before DB commit
may deliver the same link twice. The database consumes that link at most once.

`TRACKER_VERIFICATION_LIFETIME_SECONDS` defaults to 3600 on the API. Expiry is persisted, so the
worker does not need the same setting. Expired pending records are cleaned in batches of 500
when no mail is due. Monitor `confirmation_delivery_retry`, `mail_database_unavailable`, worker
liveness, and oldest unsent `next_attempt_at`/queue length. Do not log or export request bodies,
SMTP message contents, database parameters, password hashes, or confirmation tokens.

## Abuse limits and proxy trust

`TRACKER_REDIS_URL` defaults to `redis://localhost:6379/0`; Compose uses internal `redis:6379`.
All API replicas must share the same Redis database, secret and limit settings. Lua atomically
checks both budgets and increments both only when admitted. All admitted requests count,
including successful authentication; successes never reset counters. Denied requests do not
consume the other counter and do not extend expiry. Each counter's 900-second fixed window
starts with its first admitted attempt. At the boundary, up to two windows' budgets may occur
close together; this is a fixed-window limiter, not a sliding-window limit.

| Operation | Identifier budget | Address budget | Settings (prefix `TRACKER_`) |
| --- | --- | --- | --- |
| Login | 10 / normalized email | 100 | `LOGIN_ACCOUNT_LIMIT`, `LOGIN_ADDRESS_LIMIT` |
| Register | 3 / normalized email | 20 | `REGISTER_ACCOUNT_LIMIT`, `REGISTER_ADDRESS_LIMIT` |
| Verify email | 10 / signed request ID | 100 | `VERIFY_ACCOUNT_LIMIT`, `VERIFY_ADDRESS_LIMIT` |

`AUTH_WINDOW_SECONDS` changes the shared window length. Invalid confirmation tokens share an
`invalid` identifier budget. Email identifiers are stripped and case-folded, just like storage.
IPs are canonically compressed; IPv4-mapped IPv6 shares its IPv4 counter. Counters use HMACs,
not plaintext email/IP. Validly shaped requests are limited before hashing/database access;
malformed schema inputs receive 422 without performing those expensive operations.

Throttling returns 429 and integer `Retry-After` seconds (maximum remaining exhausted window).
Redis connection/command failure returns 503 and permits no authentication or registration
side effects. There is no in-memory fallback. Keep AOF and `maxmemory-policy noeviction`,
restrict Redis access, monitor failures and capacity, and avoid flushing limiter keys during
incidents. Loss of Redis state or changing the shared secret resets counters. A targeted
account may be denied access until its current window expires.

The socket peer is authoritative unless it is explicitly trusted via
`TRACKER_TRUSTED_PROXY_NETWORKS` (Compose: `TRUSTED_PROXY_NETWORKS`, JSON CIDR/IP list).
Resolve the deployed frontend/proxy IP, configure its exact `/32` or `/128` where possible,
and update the setting if that IP changes. Example for an operator-controlled private proxy:
`TRUSTED_PROXY_NETWORKS=["172.20.0.10/32"]`. Do not copy the example without checking your network.
Empty (default) is fail-safe: all users behind a proxy share that proxy's address budget.
Broad private CIDRs also trust other containers in those networks; restrict network access.
Universal trust (`0.0.0.0/0`, `::/0`) is rejected. Forwarding chains are walked right-to-left
through trusted hops only. Public nginx overwrites `X-Forwarded-For` with its socket peer;
Uvicorn is started with `--no-proxy-headers` so it cannot pre-trust an unverified header.
If another proxy sits in front of nginx, configure its real-IP handling explicitly.

## Password policy and offline compromised-password alternative

New registrations require 12–128 Unicode characters, reject whitespace-only strings and
accept passphrases without mandatory character classes. Passwords are not trimmed or normalized.
Existing passwords, including historical shorter ones, remain valid at login.

The bundled short common-password baseline is **not a comprehensive breach database**.
For shared/production deployments maintain a vetted local blocklist of compromised passwords
and point `TRACKER_BREACHED_PASSWORD_FILE` to its UTF-8-password SHA-256 hashes: one 64-character
hex digest per ASCII line, without counts, comments or headers. Matches are exact (case-sensitive
passwords). This is an offline alternative, not an online breach lookup; the application sends no
passwords or password-derived queries externally. A password absent from the list may still have
been breached. Do not use the toy baseline as a claim of complete breach coverage.

Obtain/update your organization's approved offline corpus through a secure administrative process;
normalize its format outside the API. Mount the hash-only file read-only into each API container,
set `TRACKER_BREACHED_PASSWORD_FILE` in a Compose override, and restart every API replica after
updates. A configured unreadable or malformed file fails registration closed with 503. The
corpus is loaded off the event loop and cached in process memory; size it to available memory.
Verify a known listed test password is rejected before serving registrations. SHA-256 here is
only a blocklist lookup format: stored user/password-request credentials remain Argon2id.

The non-secret configured dummy hash uses the current Argon2 parameters. An override through
`TRACKER_AUTH_DUMMY_HASH` is validated against the hashing library's current settings; regenerate
it when intentionally changing the hashing policy. Unknown accounts, inactive users, and wrong
passwords each perform one verification and return the same 401 detail. Historical hashes may
have different work factors, so this is equivalent algorithmic work, not a wall-clock guarantee.


## Sessions, recovery and deactivation (TASK-022)

Apply migration `0014_auth_sessions` and update API, frontend and registration-mail-worker together.
The worker now sends reset mail and cleans expired session/refresh history too. Existing JWTs are
incompatible; users sign in again once. User/password data stays unchanged. Downgrading to 0013
removes sessions and reset requests; it does not revert password changes or account deactivation.

There is no default signing secret. Generate one with `openssl rand -hex 32`, set AUTH_SECRET_KEY
(Compose) or TRACKER_AUTH_SECRET_KEY (direct processes), and use the same value on every API and
worker. Startup checks length/diversity/known placeholders, not provable entropy. All environments
require a key; do not commit it. Rotate it if compromised and also purge/revoke sessions and email
actions: opaque refresh cookies survive key rotation unless their server sessions are revoked.

Set PUBLIC_APP_URL to the exact browser-facing HTTPS URL. Compose uses it for both CSRF origin
validation and CORS. The supported deployment serves frontend and API from the same origin.
Refresh cookies always use Secure/HttpOnly/SameSite=Strict. Remote plain-HTTP/IP deployments cannot
retain these cookies: put TLS termination before the bundled frontend. Localhost development may
use the browser's loopback secure-cookie exception; use local HTTPS where unsupported.
Login/refresh/logout clients must send `Origin: <public origin>` and `X-CSRF-Protection: 1` and
retain cookies. Never configure a wildcard origin. Access JWTs are for Authorization headers only.

Direct-process settings (TRACKER_ prefix): ACCESS_TOKEN_EXPIRE_MINUTES defaults to 5 (1–15),
REFRESH_EXPIRE_DAYS to 30 (1–90, absolute server lifetime), AUTH_ISSUER to freeselftrack,
AUTH_AUDIENCE to freeselftrack-api, RESET_LIFETIME_SECONDS to 1800 (60–3600). Defaults are sufficient
for Compose; advanced overrides must be consistent between replicas. Changing JWT claim settings
invalidates existing access tokens. The reset worker reconstructs credentials using the same key.

Forgot-password request budgets are RESET_ACCOUNT_LIMIT=3 and RESET_ADDRESS_LIMIT=20. Submission
uses VERIFY_ACCOUNT_LIMIT/VERIFY_ADDRESS_LIMIT, with a reset-specific identifier; current-password
confirmation shares login budgets. New passwords use the same policy as registration. Mail failures
retry as before; monitor reset_delivery_retry and reset_delivered without logging message contents.

The Profile page exposes password change and deactivation. Both require current password and sign
out all devices. Deactivation blocks owners even of soft-deleted resources: restore and transfer
those resources first. No reactivation UI/API is provided. Lost/replayed refresh responses require
sign-in again. Web Locks coordinate tabs in supporting browsers; otherwise competing refreshes
may conservatively revoke a family. Access and refresh tokens never enter localStorage or URLs.
Email reset actions use the approved fragment convention and are removed before POST submission.
