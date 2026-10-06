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
Without `TEST_POSTGRES_URL`, the three PostgreSQL tests skip explicitly. Historical TASK-021 round trips must pin `0013_pending_registrations` before downgrading
to `0012_task_links`; current head has a deliberately irreversible owner contract migration.

Frontend, from `frontend/`: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`.
If the existing dependency cache is read-only, use `npm test -- --no-cache` and build to a writable
output directory. To avoid altering an unavailable backend `.venv`, set `UV_PROJECT_ENVIRONMENT`
to a dedicated temporary environment for all uv commands.


TASK-022: `uv run pytest -q tests/test_sessions.py tests/test_sessions_integration.py` covers
JWT validation, cookie/CSRF behavior, logout, replay, password/reset and disabled self-deactivation. TEST_POSTGRES_URL enables real races for refresh replay, password-change vs login,
one-time reset and rejected employee creation/self-deactivation. Use only a disposable migrated database.
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

## Administration contract design (TASK-029; documentation only)

The target behavior is specified in [ADR-014](../architecture/decisions/014-administration-membership-and-archive.md),
[access matrix and paper scenarios](../architecture/administration-access.md),
[API contracts](../architecture/api.md#administration-target) and
[migration plan](../architecture/administration-migration.md). It is **not implemented**.
TASK-029 validation: local Markdown links/anchors introduced by the change, task dependency
DAG (029–038), requirement-to-stage mapping, role/state scenarios and `git diff --check`.
Application tests are not required for this documentation-only stage. Architectural/product/task
folders are currently Git-ignored; compare their before/after files too, because ordinary git
diff does not include them. Existing unrelated broken links are not a reason to rewrite history.

Future implementation checks must replace conflicting old expectations, while preserving
unaffected security coverage:

* 030: PostgreSQL administrative-audit INSERT/rollback and forbidden UPDATE/DELETE/TRUNCATE,
  multi-field aggregation, distinct targets, excluded credentials/email/IP and no-op behavior.
* 031: empty/nonempty ADMIN_*, non-EmailStr config login, short/config password compatibility,
  repeat/concurrent bootstrap, admin switch, owner backfill including inactive/archived data;
  no owner/last-manager constraint. Update existing owner workflow tests to SA/OM/PM.
* 032: registration/reset/deactivate disabled including old signed actions, create+membership
  atomicity, temporary password repeated login and restricted API enumeration, reset/revoke,
  global OM block including equal-level targets, protected admin, unblock without grants.
* 033: active global maximum role and local scope independently, last-role removal, unique
  membership, preserved assignments/contextual reasons, re-add without assignment history.
* 034: all matrix read/search/board/history/chat/link/file paths; changed reporter/assignee
  candidates already in org/project; watcher/mention read candidates without autojoin;
  direct forged IDs and membership revocation between selection and commit; workflow FK.
* 035: archived-only retained read, no mutations/notifications for any role, pending scanner
  waits for active parents, cascade rollback, restore parent order and whole-org membership
  invalidation; concurrency against task creation/comment/login/notification/member addition.
* 036: authenticated user cards/all active membership names without granting resource access,
  self/SA profile, latest six-hour email token, expiry/replay/races/unique email, local SMTP sink,
  direct admin email and config-admin protection; token/password absence in UI storage/logs.
* 037: per-entity authorization on every page, user audit self/SA only, fixed 20 entries,
  same timestamps with UUID ordering, insertion between pages, empty pages, no global API.
* 038: disposable PostgreSQL upgrade from legacy + clean install; preserve TaskHistory,
  SecurityEvent, workflow, task IDs/participants, chat and MinIO references. Rehearse backups
  and rollback limitations, coordinated API/SPA/SMTP/deadline/scanner/cleanup startup; run
  full backend/frontend validation and applicable existing real-service integration suites.

Existing test modules to adapt include `test_task_domain.py`, `test_task_planning.py`,
`test_chat.py`, `test_sessions.py`, `test_auth.py`, `test_audit.py` and their integration tests;
frontend MembersPage/Workspace/ParticipantMutationErrors/SessionLifecycle/TaskChat suites.
Do not mark their existing runs as verification of target behavior. Use the commands above
from backend/frontend and record actual results in the owning implementation task. Migration
numbers are selected from actual head; TASK-029 has no runnable new migration to validate.


## Administrative audit foundation (TASK-030)

Implemented producer contract and rollback/immutability limits:
[administrative-audit.md](administrative-audit.md). TASK-031–036 producers and TASK-037
HTTP/UI remain pending; the target-model scenarios above are not all implemented.

```sh
# backend/
uv run pytest -q tests/test_administrative_audit.py
RUN_ADMINISTRATIVE_AUDIT_INTEGRATION=1 RUN_AUDIT_INTEGRATION=1 \
  uv run pytest -q tests/test_administrative_audit_integration.py tests/test_audit_integration.py
```

37 focused tests cover allowlisted actions/fields/typed values, rejected sensitive data,
user/bootstrap identity, aggregation/no-op, entity separation, shared operation correlation,
rollback/failed audit insertion and fixed 20-row keyset pagination with equal timestamps and
intervening inserts. The new PostgreSQL test uses its own disposable container. It seeds 0018
with real old events, validates 0019 upgrade/downgrade/upgrade without altering old journals,
restricted-role INSERT/atomic rollback/UPDATE/DELETE/TRUNCATE protection and safe refusal of
nonempty downgrade. It does not touch the shared database. The existing TASK-025 integration
test must also pass at the new migration head. Without opt-in flags both tests skip explicitly.

Use UV_PROJECT_ENVIRONMENT and UV_CACHE_DIR under /tmp if the workspace .venv/cache is
unavailable. A dedicated pytest --basetemp under /tmp also isolates local Redis Unix sockets.
Application migrations were exercised only in disposable PostgreSQL; no new frontend checks
are required because TASK-030 adds no frontend or HTTP endpoints.

## TASK-031 role and bootstrap validation

From backend/:

```sh
uv run pytest -q
RUN_ROLES_INTEGRATION=1 RUN_AUDIT_INTEGRATION=1 RUN_ADMINISTRATIVE_AUDIT_INTEGRATION=1 \
  uv run pytest -q tests/test_administration_roles.py tests/test_administration_roles_integration.py \
  tests/test_audit_integration.py tests/test_administrative_audit_integration.py
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

The roles suite creates its own disposable PostgreSQL 16 container, upgrades legacy and empty
schemas, checks owner backfill for inactive/archived/missing memberships, preserves old audit,
and races five bootstrap starts and password bootstrap versus old-password login. It never
migrates the shared Compose database. SQLite/API tests cover required config, non-email/long
credentials, startup, repeated bootstrap, email switch, unblocking without reactivating grants,
credential protection, audit rollback and scoped workflow/global levels. Test ADMIN_* are
synthetic fixture values, never deployment defaults. Without flags external tests skip explicitly.

The 0019 migration suite is pinned to that revision and seeds pre-role data using frozen SQL,
so current models are not run against an old schema. Audit runtime protection also runs at the
current head. 0020/0021 deliberately reject downgrade; do not force an owner reconstruction.

Frontend: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`. Capability fixtures
replace owner_id; tests cover scoped workflow controls and config-admin credential UI.
If the existing .venv/cache is read-only, use a temporary UV_PROJECT_ENVIRONMENT and UV_CACHE_DIR.
