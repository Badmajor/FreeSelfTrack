# Testing

Backend uses Python 3.13+ and uv. From `backend/`:

```sh
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

Focused TASK-021 validation is `uv run pytest -q tests/test_auth.py`.
Tests use an isolated SQLite database and real Lua through fakeredis. No external email is sent.
The SMTP test uses a local TCP mail sink. `test_auth_integration.py` also runs a disposable local
redis-server over a Unix socket when the executable is installed.

For PostgreSQL concurrency tests, provision a **disposable empty database**, migrate it with
`TRACKER_DATABASE_URL=<postgresql+asyncpg URL> uv run alembic upgrade head`, then run:

```sh
TEST_POSTGRES_URL=<disposable postgresql+asyncpg URL> uv run pytest -q tests/test_auth_integration.py
```

These tests create users and registration rows; never point them at a production/shared database.
They check concurrent single-use confirmation, unique-email races and SMTP worker locking.
Without `TEST_POSTGRES_URL`, the three PostgreSQL tests skip explicitly. Validate downgrade to
`0012_task_links` and upgrade to head on that disposable database before removing it.

Frontend, from `frontend/`: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`.
If the existing dependency cache is read-only, use `npm test -- --no-cache` and build to a writable
output directory. To avoid altering an unavailable backend `.venv`, set `UV_PROJECT_ENVIRONMENT`
to a dedicated temporary environment for all uv commands.


TASK-022: `uv run pytest -q tests/test_sessions.py tests/test_sessions_integration.py` covers
JWT validation, cookie/CSRF behavior, logout, replay, password/reset/deactivation and ownership
boundaries. TEST_POSTGRES_URL enables real races for refresh replay, password-change vs login,
one-time reset and deactivation vs ownership creation. Use only a disposable migrated database.
Migration 0014 should upgrade, downgrade to 0013_pending_registrations, and upgrade again.
Frontend lifecycle tests: `npm test -- --no-cache src/test/SessionLifecycle.test.tsx`.

The existing `alembic check` baseline reports old metadata differences for users' email uniqueness,
ix_tasks_slug_lookup and ix_notifications_recipient_unread. TASK-022 adds no reported drift;
upgrade/downgrade and the new tables' constraints are validated separately.

TASK-023 ASGI/configuration checks: `uv run pytest -q tests/test_browser_security.py tests/test_sessions.py`.
Real nginx/Chrome/TLS/Compose checks are opt-in and create/remove isolated Docker containers and a
network, a temporary self-signed certificate, and a temporary Chrome profile. They do not restart
or migrate the shared stack. Requirements: Docker, openssl, installed Chrome, cached
`python:3.13-slim` and `nginx:1.27-alpine` images, and a production SPA build:

```sh
# Repository root:
(cd frontend && npm run build -- --outDir /tmp/fst023-frontend-build)
cd backend
RUN_BROWSER_SECURITY=1 BROWSER_SECURITY_DIST=/tmp/fst023-frontend-build \
  BROWSER_SECURITY_CHROME=/opt/google/chrome/chrome \
  uv run pytest -q tests/test_browser_deployment.py
```

The fixture upstream isolates proxy headers/attachment delivery; ASGI tests separately cover real
CORS, authenticated reads and CSRF. Chrome executes the actual built SPA and verifies inline-script
and frame blocking. TLS checks verify the temporary certificate, HTTPS-only HSTS and a fixed-host
HTTP 308 redirect. Compose checks render with synthetic settings, without printing configuration
or secrets. Without RUN_BROWSER_SECURITY these four deployment tests explicitly skip.


TASK-024/TASK-026 checks:

```sh
# backend/
uv run pytest -q tests/test_chat.py tests/test_attachment_hardening.py
# Requires Docker Compose and the pinned MinIO/PostgreSQL images; creates isolated
# projects/volumes, uses synthetic credentials and removes them even after failure.
RUN_ATTACHMENT_INTEGRATION=1 uv run pytest -q tests/test_attachment_integration.py
# Also build/start real backend + nginx frontend + cleanup worker and test HTTP transfers:
RUN_ATTACHMENT_INTEGRATION=1 RUN_ATTACHMENT_STACK=1 uv run pytest -q tests/test_attachment_integration.py
# frontend/
npm test -- --no-cache src/test/TaskChat.test.tsx
```

Without RUN_ATTACHMENT_INTEGRATION the container tests skip; the full image-build smoke test
additionally requires RUN_ATTACHMENT_STACK. On Docker installations without buildx, export
DOCKER_BUILDKIT=0 and COMPOSE_DOCKER_CLI_BUILD=0 if the engine still supports the legacy builder.
Tests never restart/migrate the shared Compose project. They exercise native bucket creation,
private access, persistence on restart, bounded multipart transfer, partial-upload cleanup,
0015 transfer with checksum-failure recovery, 0016 refusal before transfer, contract downgrade/
upgrade, quarantine release and PostgreSQL advisory-lock races. API tests additionally cover
IDOR, organization revocation, soft deletion, corrupt rasters, capacity/size/time limits,
transaction failure, idempotency, attachment order and connection cleanup on disconnect.

## Automatic attachment scanning (TASK-027)

From `backend/`, run `uv run pytest -q` for scanner protocol/state regressions.
The frontend suite covers automatic availability refresh without clicking the manual button.
Optional Docker checks create disposable projects and remove their volumes:

```sh
RUN_ATTACHMENT_SCAN_INTEGRATION=1 uv run pytest -q tests/test_attachment_scan_integration.py
RUN_ATTACHMENT_INTEGRATION=1 RUN_ATTACHMENT_STACK=1 RUN_ATTACHMENT_SCAN_STACK=1 uv run pytest -q tests/test_attachment_integration.py
```

The first uses real ClamAV with plain files, harmless EICAR and an EICAR ZIP. The second also
checks the HTTP upload → worker → authorized download flow with real PostgreSQL/MinIO.
Use `DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0` if the Docker host lacks buildx.

## Audit and history integrity (TASK-025)

`uv run pytest -q tests/test_audit.py` covers attribution/correlation, sanitized metadata,
no-op deduplication, atomic rollback, attachment review and history authorization.
`RUN_AUDIT_INTEGRATION=1 uv run pytest -q tests/test_audit_integration.py` creates a dedicated
PostgreSQL 16 container with synthetic credentials and removes it after the test. Requires
Docker and `postgres:16-alpine`. It checks upgrade/downgrade/upgrade, application-role history
inserts, rollback, and UPDATE/DELETE/TRUNCATE/cascade rejection on real PostgreSQL. It never
migrates or cleans the shared stack. Without the flag this test explicitly skips.
