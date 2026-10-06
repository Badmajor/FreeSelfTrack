# Administrative audit foundation (TASK-030)

Implemented: model, strict internal write schema, transaction-bound writer/repository,
fixed-size internal query and PostgreSQL migration `0019_administrative_audit`.
TASK-031 adds producers for bootstrap, current resources/memberships/workflow and guards.
Not implemented: the remaining TASK-032–036 mutations and authorized audit HTTP reads/UI
(TASK-037). Existing TaskHistory/SecurityEvent rows remain unchanged.

See [ADR-014](../architecture/decisions/014-administration-membership-and-archive.md),
[target API](../architecture/api.md#administration-target),
[access matrix](../architecture/administration-access.md) and
[transition plan](../architecture/administration-migration.md).

## Producer contract

Use `AdministrativeAuditService` with the **same AsyncSession and transaction** as the domain
mutation. Complete authorization and domain checks before staging an event. The writer does
not authorize an actor, commit, swallow persistence errors or start a separate transaction.
Failure to insert an event must fail the originating mutation, followed by rollback.

```python
from app.schemas.administrative_audit import AdministrativeAuditWrite, AuditChange
from app.services.administrative_audit import AdministrativeAuditService

# Inside the authorized profile-update service, before its final commit:
audit = AdministrativeAuditService(session)
audit.record(AdministrativeAuditWrite(
    actor_id=actor_id,
    entity_type="user",
    entity_id=user_id,
    action="profile_updated",
    changes=(
        AuditChange(field="first_name", old=old_first_name, new=new_first_name),
        AuditChange(field="last_name", old=old_last_name, new=new_last_name),
    ),
))
# The originating service commits the profile and event together.
```

One call per changed entity/subject combines all changed fields in one row. Duplicate field
names are rejected; producers must combine intermediate changes into final before/after values.
Unchanged fields are dropped; an empty effective change returns None and stages no row.
After an idempotent retry, producers must compare current persisted state: calling record
again with fabricated old values is not an idempotency mechanism. No retrospective backfill.

Reuse one service instance for a cascade or pass its `operation_id` to another writer.
By default it captures the HTTP server-generated request UUID; outside HTTP it generates a
fresh UUID. Never pass a client correlation ID as operation_id. Event IDs are independent UUIDs;
occurred_at is generated in UTC on insertion. User actors require actor_id; bootstrap requires
actor_kind="bootstrap" and actor_id=None. Snapshot IDs have no FK/cascade relationships.

The internal Pydantic schemas are strict/frozen, forbid unknown fields, and hide input values
in validation error text. Supply UUID/datetime objects and tuples rather than arbitrary JSON.
Callers must not log raw validation `.errors()` payloads or input objects. No writer logging
copies user input. The allowlist is not a content scanner: names/descriptions may contain
user text; callers must never place credentials into an otherwise allowed textual field.

| Entity/action | Allowed change fields |
| --- | --- |
| user/user_created | first_name, last_name, is_active, is_system_admin, organization_id, project_id, role, state |
| user/profile_updated | first_name, last_name |
| user/user_blocked or user_unblocked | is_active |
| user/system_role_changed | is_system_admin |
| organization or project/created or updated | name, description |
| project/workflow_changed | statuses: tuple of WorkflowStatusSnapshot(id, name, position, is_active, is_completed) |
| user, organization or project/member_added, member_removed, member_role_changed | organization_id, project_id, role, state; subject_user_id required |
| organization, project or task/archived or restored | archived_at, timezone-aware datetime or None |

Membership fields have typed UUIDs and enumerated role/state values. User-card membership
events require entity_id == subject_user_id. Emit an event for both the user card and the
corresponding organization/project card as specified in ADR-014. Creation by an OM combines
initial participation into user_created and emits a separate organization member_added event.
An automatic membership deactivation does not call this writer; archive cascades emit only
actual organization/project/task lifecycle events. Restore emits only the restored entity.
Workflow snapshots contain only the affected statuses, never serialized ORM objects.

Read, rejected, password/email-change, access-error and automatic-deactivation actions are not
accepted. Password, hash, token, IP, email, file/comment content and arbitrary metadata fields
are not accepted. SecurityEvent producers retain their separate technical event policy.

## Internal read query

`AdministrativeAuditRepository.page_for_entity(entity_type, entity_id, after=...)` returns
`AdministrativeAuditPage(items, next_position)`. It selects only this entity, sorts by
`occurred_at DESC, id DESC`, fetches 21 rows and returns at most 20. next_position is the
last returned (timestamp, UUID) when more rows exist. The next query uses a strict comparison,
so equal timestamps and new insertions do not cause duplicates in an existing cursor walk.
A refresh is needed for newly inserted records above the current position; this is a live feed.

This is an **internal repository query, not an authorized read service**. TASK-037 must authorize
the entity on every page, validate an opaque entity-bound cursor, resolve actor display names
without N+1 and build API schemas. Do not expose this repository through a generic audit route.
No HTTP/API contract has been activated by TASK-030.

## Migration, immutability and downgrade

0019 follows 0018. It adds one empty table, actor/entity/action CHECK constraints and an index
on entity_type/entity_id/occurred_at/id. PostgreSQL ALWAYS triggers reject UPDATE, DELETE and
TRUNCATE through the existing 0018 reject_audit_mutation function. 0018 tables, functions and
existing rows are not rewritten; no domain or auth behavior changes.

A trusted migration role applies the migration. Runtime must be non-owner/non-superuser
without DDL/trigger-disabling privileges, as in ADR-013. This is append-only protection against
runtime DML, not protection against a trusted DBA or forged application INSERTs. Retain the
journal indefinitely and include it in database backups; no retention/delete/export API exists.

Downgrade to 0018 takes an exclusive table lock and **refuses a nonempty journal**. For an
empty journal it drops only the new table/index/triggers, preserving the shared rejecting
function and both old journals. Backups do not make it safe to bypass the refusal automatically;
after real events exist use forward fixes or the coordinated backup-recovery plan. Do not
remove events/disable triggers merely to make downgrade pass.

## Validation

From backend/:

```sh
uv run pytest -q tests/test_administrative_audit.py
RUN_ADMINISTRATIVE_AUDIT_INTEGRATION=1 RUN_AUDIT_INTEGRATION=1 \
  uv run pytest -q tests/test_administrative_audit_integration.py tests/test_audit_integration.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

The opt-in test creates/removes its own PostgreSQL 16 container with synthetic credentials.
It migrates to 0018, seeds real old journal rows, upgrades/downgrades/upgrades 0019, compares
old records, and tests restricted-role INSERT/rollback and rejected UPDATE/DELETE/TRUNCATE.
It also verifies failed audit insertion rolls back a user mutation and a nonempty downgrade
leaves schema/version/data intact. It does not use or migrate the shared Compose database.
Without the flag it skips explicitly. SQLite tests cover schema policy, aggregation, separate
objects, no-op behavior, bootstrap identity, rollback, and 20-row pagination including tied times.

## Workflow snapshot compatibility (TASK-031)

An active status requires a nonnegative position. Inactive status snapshots may have negative
positions because the existing workflow stores archived statuses outside the active ordering.
Producers preserve these values and include only actually changed status snapshots.
Bootstrap uses actor_kind=bootstrap with actor_id=null; actual session revocations use separate
technical SecurityEvent records with the same actor kind. No credentials are audit fields.
