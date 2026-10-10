# Development Setup

> TASK-031 implements roles and required ADMIN_* bootstrap. This is an intermediate stage;
> TASK-032 removes registration/reset; the full administrative release remains TASK-033–038.
> Existing installations require the [coordinated migration plan](../architecture/administration-migration.md).

## Docker Compose

Docker Compose starts the complete local stack:

- frontend at `http://localhost:5173`;
- backend API through the frontend at `http://localhost:5173/api`;
- PostgreSQL on `127.0.0.1:5432`;
- Redis and MinIO on the internal Compose network.

Prepare local variables and start the stack:

```bash
cp .env.example .env
# Set ADMIN_EMAIL and ADMIN_PASSWORD locally.
# Generate AUTH_SECRET_KEY with openssl rand -hex 32; configure credentials, SMTP and PUBLIC_APP_URL.
docker compose up --build
```

The backend applies Alembic migrations before starting. The deadline-worker starts after the backend healthcheck and polls for due-task notifications; configure its interval with `DEADLINE_WORKER_INTERVAL_SECONDS`. Startup dependencies use healthchecks, so the API waits for PostgreSQL, Redis, and MinIO. The database, Redis AOF, and MinIO data are stored in named volumes.

Useful commands:

```bash
docker compose ps
docker compose logs -f backend deadline-worker
docker compose down
docker compose down -v  # removes local data volumes
```

Set `FRONTEND_PORT` or `POSTGRES_PORT` in `.env` when the default host ports are busy. Keep `AUTH_SECRET_KEY`, database credentials, and MinIO credentials overridden with strong values outside local development.

## Local processes

Backend development uses `uv` from `backend/`; set `TRACKER_DATABASE_URL` in the backend environment before starting it directly. The Compose backend receives its internal `db:5432` URL from environment variables; the published PostgreSQL host port is only for external debugging. Frontend development uses npm from `frontend/`. The Vite dev server proxies `/api` to `http://localhost:8000`, matching the same-origin URL used by the Compose frontend.


## Account provisioning

Set ADMIN_EMAIL and ADMIN_PASSWORD, migrate to head, then start the API. In **Users**, SA can
create accounts globally or in an organization; OM creates in their managed organization.
Creation returns a temporary password once, without mail. The user signs in, sets a permanent
password, then signs in again. Only SA issues replacement temporary passwords (except config admin).
Public register/verify-email/reset-request/reset/deactivate routes return 404, including old links.
Migration 0022 clears pending registration/reset requests. The legacy mail-worker service now
performs expired-session cleanup only; replace old worker images during the coordinated upgrade.
Block/unblock is global for SA/OM; block revokes sessions and memberships but retains task IDs.
Unblock never restores memberships. Do not apply migrations to a shared database during testing.

## Session security upgrade

Before starting any service, generate AUTH_SECRET_KEY with `openssl rand -hex 32`; `.env.example`
leaves it empty and Compose has no fallback. Direct backend processes use TRACKER_AUTH_SECRET_KEY.
Set PUBLIC_APP_URL to the browser-facing origin; shared deployments require HTTPS so Secure refresh
cookies work. Keep API and frontend on the same origin and deploy migration 0014 with both services
and the mail worker. Existing users must sign in once after upgrading. See authentication.md.

## Browser transport baseline (TASK-023)

The default Compose HTTP port now binds `127.0.0.1`, not all interfaces. Set `PUBLIC_HOST=localhost`
and `PUBLIC_APP_URL=http://localhost:5173` for local use. Open that exact address for CSRF checks.
Changing FRONTEND_PORT requires updating PUBLIC_APP_URL. PUBLIC_APP_URL must be an exact origin
(no trailing slash/path/query/fragment). PUBLIC_HOST is the hostname only (no scheme or port).

For a shared deployment on a Linux host:

1. Set `PUBLIC_HOST=tracker.example.com`, `PUBLIC_APP_URL=https://tracker.example.com` and
   `FRONTEND_BIND_ADDRESS=127.0.0.1`; keep FRONTEND_PORT=5173 for the supplied example.
2. Provision a trusted TLS certificate with renewal on the host. Adapt
   `deploy/nginx-tls.conf.example` to your hostname and certificate paths, install it in the host
   nginx `http` context, run `nginx -t`, and reload your terminator. Keep private keys outside Git.
3. Run Compose normally. Expose only the terminator's ports 80/443. The example redirects HTTP to
   a fixed HTTPS hostname with 308; unknown hosts are rejected. TLS terminates at the host, then
   proxies to loopback nginx. Internal HTTP carries no HSTS; the HTTPS edge adds it on all statuses.
4. Verify HTTPS SPA/deep links, login/refresh, attachment downloads and security response headers.
   Never publish backend port 8000 or expose the internal HTTP frontend alongside the HTTPS edge.

For a containerized/external terminator, adapt upstream networking and firewall access explicitly;
127.0.0.1 inside another container is not the host. Do not simply enable trust for all forwarded
headers. Default client rate limits aggregate behind the proxy; see authentication.md for exact
trusted-peer real-IP configuration. The example does not claim to preserve the original client IP.

Direct backend processes use `uv run uvicorn app.main:app --no-proxy-headers`.
`TRACKER_TRUSTED_HOSTS` is a JSON list of additional exact hosts; the public hostname is included
automatically. Defaults are localhost, 127.0.0.1 and IPv6 loopback. Wildcards are rejected.
`TRACKER_CORS_ORIGINS` is a JSON list of exact browser origins; Compose derives it from PUBLIC_APP_URL.
The SPA uses same-origin requests. Vite development is not the hardened production server.
Interactive `/docs` and `/redoc` are disabled by the restrictive API CSP; `/openapi.json` remains.
See ADR-010 for policies and deployment tradeoffs.


## MinIO attachments (TASK-024 / TASK-026)

MinIO creates `S3_BUCKET` (default `tracker-attachments`) with `MINIO_DEFAULT_BUCKETS` through
its native startup. Keep the pinned image's default command and mount `minio_data` at
`/bitnami/minio/data`. The old custom command bypasses bucket creation. No init/provision
sidecar, dedicated S3 identity/policy, or lifecycle configuration is installed. Backend and
attachment-cleanup-worker use the existing MINIO_ROOT_USER/MINIO_ROOT_PASSWORD internally.
The MinIO healthcheck also verifies the configured bucket exists; do not publish S3/console ports.

New installations can start normally. **Existing bytea attachments require a maintenance-window
transfer at migration 0015 before upgrading to head.** See [attachment operations](attachments.md)
for exact cutover, quarantine review, resource limits, backup/restore and rollback instructions.
New and migrated files remain pending until the automatic ClamAV worker verifies and releases them.
The default Compose stack includes ClamAV and the scan worker; see attachments.md for operation and retries.

## Configuration administrator and roles (TASK-031)

Set nonempty `ADMIN_EMAIL` and `ADMIN_PASSWORD` in your local environment or `.env` before
starting Compose/API. These names have **no TRACKER_ prefix**. Do not commit credentials.
No email-format or password-complexity policy applies to this account; login accepts its
configured identifier and password. Ordinary permanent-password policy remains unchanged.

After migrations, API startup runs bootstrap before serving health/API requests. It creates or
reuses the normalized (`strip().casefold()`) identifier, unblocks it, clears the temporary-password
flag and applies the configured Argon2 password. Restarting with unchanged credentials preserves
sessions. Changing credentials or the system role revokes affected sessions and pending email
actions. Changing ADMIN_EMAIL selects another account, preserving both accounts' memberships and
local roles; it does not rename the old account or reactivate revoked memberships.
All replicas must receive identical configuration. Administrator credentials can only be changed
by updating ADMIN_* and restarting; profile password changes, email reset and self-deactivation
cannot alter this account. Self-deactivation is disabled for everyone.

Migrations `0020_administration_roles` and `0021_remove_ownership` replace owner_id with
member/manager roles and active/archived/revoked membership states. Inactive users and archived
scopes do not acquire active grants. Zero or multiple managers are valid; creating organizations
(SA only) or projects (SA/scoped OM) does not add the creator. Workflow changes require SA, scoped
OM or scoped PM. Transfer-ownership endpoints are removed; clients use backend capabilities.
Downgrade cannot reconstruct ownership; use a coordinated pre-transition backup if needed.

This is an intermediate development stage. Membership UI, complete read matrix, archive lifecycle and audit views remain TASK-033–037. Registration and email recovery are disabled by TASK-032. Do not deploy this intermediate stage over a shared existing
installation: follow the [coordinated migration plan](../architecture/administration-migration.md).
