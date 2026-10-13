> TASK-032 replaces obsolete registration/reset expectations with administrative provisioning,
> restricted-session and legacy-link rejection tests. Historical TASK-021/022 mail/confirmation
> commands below describe earlier releases; use the TASK-032 checks for current lifecycle behavior.

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
[migration plan](../architecture/administration-migration.md). This section records the historical design stage; TASK-031–037 are now implemented.
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
[administrative-audit.md](administrative-audit.md). TASK-031–036 producers and TASK-037 HTTP/UI are implemented. Release evidence is recorded below.

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


## TASK-032 administrative user lifecycle

Backend: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`.
Focused: `uv run pytest -q tests/test_user_lifecycle.py tests/test_auth.py tests/test_sessions.py`.
Existing domain fixtures seed pre-existing accounts directly; provisioning tests use the real API.
Coverage includes all registered protected routes under a restricted session, repeated temporary
login, change/relogin, one-time secrets/no-store, role/scope validation, peer OM blocking, protected
SA, preserved assignments/history, revoked access/refresh/memberships, no-op audit and rollback,
blocked reset, old signed link rejection and filter-bound directory pagination.

`RUN_USER_LIFECYCLE_INTEGRATION=1 uv run pytest -q tests/test_user_lifecycle_integration.py`
creates/removes its own PostgreSQL 16 container with synthetic credentials. It verifies 0022
upgrade/downgrade/upgrade invalidates pending actions and races duplicate creation, reset/change,
and block/login. It never accesses the shared database; no flag means an explicit skip.
The prior TASK-021 confirmation concurrency tests are replaced by these current lifecycle races;
the real Redis limiter test and session rotation/change races remain.

Frontend: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`.
Auth/UsersPage tests cover disabled fragments, forced change before workspace requests, password
visibility/dismissal without storage, capability-controlled actions, block confirmation and readable
assignee strike-through. Use `npm test -- --no-cache` and build under /tmp for read-only caches.


## TASK-033 membership administration

Backend: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy app`. Focused: `uv run pytest -q tests/test_membership_administration.py`.
API coverage includes strict UUID/role schemas, SA/OM/PM scope and global hierarchy including
peer roles elsewhere, SA self-management, last-manager demotion, no duplicates on re-add,
all-or-nothing initial managers, paired/no-op audit, audit-failure rollback, parent/archive guards,
filter-bound keyset pagination, preserved participant IDs/history and contextual assignee reasons.
Additional regressions prove participant/watcher requests cannot implicitly create membership.
Existing workflow, attachment, task and audit tests use the new membership DTO and 204 DELETE.

```sh
# backend/: every enabled suite creates and removes its own disposable PostgreSQL container.
RUN_MEMBERSHIP_INTEGRATION=1 uv run pytest -q tests/test_membership_administration_integration.py
RUN_ROLES_INTEGRATION=1 RUN_USER_LIFECYCLE_INTEGRATION=1 \
RUN_ADMINISTRATIVE_AUDIT_INTEGRATION=1 RUN_AUDIT_INTEGRATION=1 \
uv run pytest -q tests/test_administration_roles_integration.py \
  tests/test_user_lifecycle_integration.py tests/test_administrative_audit_integration.py \
  tests/test_audit_integration.py
```

The new suite verifies 0023 upgrade/downgrade/upgrade, null legacy descriptions, preserved
resource data and five concurrent upserts per scope with one unique membership and one audit
pair. Old migration-specific tests pin their own revision when checking its downgrade contract;
clean-role/bootstrap and runtime audit checks still run against current head. No shared database
is used or migrated. Opt-in suites skip without flags. Restricted environments may require
running SQLite/asyncio tests outside the sandbox; retain synthetic isolated fixtures.

Frontend: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`.
Membership tests cover UUID manager assignment, demotion, organization removal, hierarchy errors,
duplicate-submit prevention, capability controls, direct project route, retry/pagination and
contextual strike-through/re-add. Resource creation tests cover descriptions and optional managers.
Participant/mention selectors consume paginated membership DTOs and allow loading more candidates.
Use `--no-cache` for tests and `--outDir /tmp/fst033-frontend-build` for builds if local caches/output
are read-only. No new dependencies are required.


## Task read/write/chat access (TASK-034)

`tests/test_task_access.py` covers SA/global OM/local PM/employee/org-only/outsider/revoked/
archived-role active-resource scopes, task capabilities, protected ready/pending files, all-field
editing independently of authorship, archive guard identity checks, candidate pagination and
validation, cross-project status rejection, creation without reporter membership, watcher without
autojoin, IDOR/search/link/history leaks, preserved assignments and notification revocation.
Existing task/planning/chat/attachment expectations now follow the active role matrix.

```sh
# backend, disposable SQLite by default:
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app
# Disposable PostgreSQL 16 container; never uses the shared database:
RUN_TASK_ACCESS_INTEGRATION=1 uv run pytest -q tests/test_task_access_integration.py
# Existing private-storage and real ClamAV integrations:
RUN_ATTACHMENT_INTEGRATION=1 RUN_ATTACHMENT_SCAN_INTEGRATION=1 \
  uv run pytest -q tests/test_attachment_integration.py tests/test_attachment_scan_integration.py
# frontend:
npm test
npm run lint
npm run typecheck
npm run build
```

The PostgreSQL test verifies a comment started after stale authorization waits for membership
revocation and rejects the stale mention atomically; no message/notification leaks through.
It also exercises JSON text extraction and link-history filtering on real PostgreSQL, not just
SQLite. `TaskAccess.test.tsx` covers unrelated-member editing, reader-only chat, denied publication
and explicit reporter selection by a manager without membership. Link deletion uses pair-specific
backend permission. This stage has no schema migration; full HTTP scanner stack remains opt-in
with RUN_ATTACHMENT_STACK/RUN_ATTACHMENT_SCAN_STACK as described above.


## Archive lifecycle (TASK-035)

```sh
# backend/
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app
RUN_ARCHIVE_INTEGRATION=1 uv run pytest -q tests/test_archive_lifecycle_integration.py
# frontend/
npm test
npm run lint
npm run typecheck
npm run build
```

`test_archive_lifecycle.py` verifies scoped cascade/no-op audit, preserved participants/status/order,
archived-only retained roles, membership revocation after parent restoration, all three employee
identity guards, role denial, state pagination, deadline suppression, ready-file reading, scanner
pause/resume, manual-review rejection, assignee reasons/re-add, link/history filtering and rollback.
Existing lifecycle tests now use POST archive and page envelopes while retaining audit/storage guards.
`test_archive_lifecycle_integration.py` provisions/removes disposable PostgreSQL 16 containers,
checks legacy normalization and unchanged history/task data, explicit unsafe-downgrade refusal,
audit-failure rollback and archive versus creation/comment/deadline races after stale authorization.
It never migrates the shared database; without RUN_ARCHIVE_INTEGRATION it explicitly skips.
Frontend archive regressions verify backend capabilities, confirmation of membership revocation,
restoration errors, page loading, list invalidation, task editing after restoration and separate
active/archived board cache keys. Existing board/chat/session/management tests remain.
Use writable temporary UV_PROJECT_ENVIRONMENT/UV_CACHE_DIR and frontend --no-cache/--outDir
when local environment, caches or build output are read-only.


## User cards and email (TASK-036)

Focused API/SMTP: `uv run pytest -q tests/test_user_cards.py tests/test_email_change_mail.py
 tests/test_user_lifecycle.py` (one line, from backend/). Tests cover full-session-only cards,
blocked targets, cross-resource names without grants, inactive membership filtering and bound
pagination; self/SA profile and rejected manager/extra fields, atomic/no-op audit; six-hour
expiry, replacement, ownership, replay, uniqueness, direct changes, protected config admin,
block/reset cancellation, sanitized token validation, real local TCP SMTP delivery and retries.

```sh
# backend: isolated PostgreSQL containers for new email and affected lifecycle/bootstrap suites
RUN_USER_CARDS_INTEGRATION=1 RUN_USER_LIFECYCLE_INTEGRATION=1 RUN_ROLES_INTEGRATION=1 uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app
# frontend
npm test -- --no-cache
npm run lint
npm run typecheck
npm run build -- --outDir /tmp/fst036-frontend-build
```

The email suite tests 0025 upgrade/downgrade/upgrade, preserved users, CASCADE FK, serialized
replacement/single-use confirmations, concurrent claims on one address, direct-vs-self changes,
bootstrap cancellation and SKIP LOCKED SMTP selection. It never accesses the workspace database.
Older migration checks stay pinned for historical assertions, then upgrade to head before
running current bootstrap/lifecycle services. PATCH on the new GET-only card URL returns 405;
the system-role mutation regression still ensures there is no write route.

Frontend UserCardPage/EmailChangeConfirmation tests cover names vs links, pagination, backend
errors, editing controls, direct/self API selection, explicit confirmation after login,
fragment removal, absence of token storage, success/cancel and duplicate-submit prevention.
Full result on 2026-10-12: 230 backend passed / 17 unrelated opt-in skips; 85 frontend passed;
all lint/type/format/build checks passed. Use UV_PROJECT_ENVIRONMENT and UV_CACHE_DIR in /tmp
if the supplied environment is read-only; asyncio/SMTP may require execution outside sandbox.
See [operations](user-cards-and-email.md) for delivery/rollback limitations.


## TASK-037 entity audit views

From backend/: `uv run pytest -q tests/test_audit_views.py` covers entity/self/SA access,
archive preservation and revocation, full-session requirements, fixed 20-row keyset pages,
tied timestamps, concurrent insertion, empty pages, cursor/query validation, actor fallback,
paired membership events and cascade correlation through actual HTTP endpoints.
Run the full backend suite and Ruff/format/mypy commands above. Preserve the PostgreSQL
regression: `RUN_ADMINISTRATIVE_AUDIT_INTEGRATION=1 RUN_AUDIT_INTEGRATION=1 uv run pytest -q
tests/test_administrative_audit_integration.py tests/test_audit_integration.py` (single command).
It creates disposable PostgreSQL containers and checks old data and append-only protections.
No TASK-037 migration or shared database changes are required.

From frontend/: `npm test -- --no-cache src/test/EntityAudit.test.tsx` checks aggregation,
loading/error/retry/empty states, previous/next/refresh and entity-switch pagination reset.
Run `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` for regression.
If the repository's environment is unusable, use a temporary UV_PROJECT_ENVIRONMENT;
`uv run --no-sync` is appropriate for an already provisioned matching environment.

## TASK-038 complete release acceptance

Use the [requirement-to-test record](administration-validation.md) for all 60 parent criteria
and the [deployment runbook](administration-release.md) for backup, cutover and runtime roles.
The current implementation includes TASK-031–037; earlier sections above are stage history.

```sh
# backend/: PostgreSQL suites create/remove disposable containers, never the shared DB.
RUN_ROLES_INTEGRATION=1 RUN_USER_LIFECYCLE_INTEGRATION=1 RUN_MEMBERSHIP_INTEGRATION=1 \
RUN_TASK_ACCESS_INTEGRATION=1 RUN_ARCHIVE_INTEGRATION=1 RUN_USER_CARDS_INTEGRATION=1 \
RUN_ADMINISTRATIVE_AUDIT_INTEGRATION=1 RUN_AUDIT_INTEGRATION=1 uv run pytest -q -rs
# Optional TEST_POSTGRES_URL enables the remaining session races; use only a disposable head DB.
# Full release: two isolated Compose projects, clean and synthetic 0018 upgrade.
RUN_ADMINISTRATION_RELEASE=1 uv run pytest -q tests/test_administration_release.py
RUN_ATTACHMENT_INTEGRATION=1 RUN_ATTACHMENT_SCAN_INTEGRATION=1 \
  uv run pytest -q tests/test_attachment_integration.py tests/test_attachment_scan_integration.py
uv run ruff check .
uv run ruff format --check .
uv run mypy app
# frontend/: npm test; npm run lint; npm run typecheck; npm run build
```

The release test requires Docker Compose, current backend/frontend build dependencies/images,
PostgreSQL 16, pinned MinIO/ClamAV, Redis, `mailhog/mailhog:v1.0.1` (test-only SMTP sink), and
Chrome at `/opt/google/chrome/chrome` or `BROWSER_SECURITY_CHROME`. Its fixture uses the real
`deploy/compose.runtime.yml`. It verifies maintenance SQL, old tokens, legacy object hashes,
owner backfill/archive normalization, real HTTP lifecycle and automatic scanning/email delivery,
runtime DDL/journal denial, and Chrome temporary-password/change/relogin plus audit pagination.
Screenshots/logs stay in pytest's temporary directory and contain synthetic data only.
It publishes random loopback test ports and removes its own containers/volumes even after failure.
No existing Compose project or external SMTP is used. Without the flag the two cases skip.

`test_archive_lifecycle_integration.py` additionally races restore with explicit new membership:
restore revokes old grants first, the waiting add survives, and repeated restore preserves it.
`test_membership_administration_integration.py` pins the 0023 migration round trip before head;
it must not attempt to downgrade through intentionally irreversible 0024.

On hosts without buildx, prefix Docker test commands with
`DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0` if legacy builds are supported.
Use a writable `UV_PROJECT_ENVIRONMENT` and `UV_CACHE_DIR` under `/tmp` where needed.
Run the existing nginx/Chrome/TLS regression with `RUN_BROWSER_SECURITY=1` and
`BROWSER_SECURITY_DIST` pointing to the current production SPA build, as described above.
Report passed and skipped suites separately; the existence of a test is not proof it ran.


TASK-038 final results (2026-10-13): full backend with administrative PostgreSQL flags,
disposable TEST_POSTGRES_URL and browser transport enabled: 247 passed / 7 opt-in skips.
The seven also passed separately: clean/upgrade release 2; storage/scanner 4 (1 full-stack skip),
then full attachment stack 3, including that skipped HTTP/scanner case. Frontend 88 passed;
Ruff/format/mypy/lint/typecheck/build and links/diff passed. The older attachment smoke now
explicitly adds its reporter to org/project through HTTP instead of assuming creator autojoin.
