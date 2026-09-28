# TASK-004: Kanban API and task workflow history

## Goal

Implement the backend Kanban API so a project exposes its ordered statuses as columns, loads column tasks independently with cursor pagination, allows project members to move tasks, and records every status transition.

## Context

The project already has `ProjectStatus`, task/status integrity checks, project authorization, and basic status endpoints. The Kanban API needs a stable aggregate contract for the frontend, scalable column loading, owner-only workflow configuration, and auditable task transitions.

The workflow remains project-owned: a `ProjectStatus` is both a task status and a Kanban column. No global status catalog or separate Kanban column entity is introduced.

References:

* `docs/product/requirements.md`
* `docs/product/glossary.md`
* `docs/architecture/overview.md`
* `docs/architecture/api.md`
* `docs/architecture/decisions/002-project-owned-statuses.md`
* `docs/architecture/decisions/004-membership-ownership-lifecycle.md`

## Requirements

### Functional requirements

* Creating a project creates these active default statuses in order: `Backlog`, `In Progress`, `Done`.
* The project owner can create, rename, reorder, archive, and restore project statuses.
* A project member can read active project statuses and the Kanban board.
* A project member can move a task to another active status in the same project.
* Every status move records who moved the task, when it happened, the previous status, and the new status.
* The Kanban board returns ordered columns with the first page of tasks and a cursor for each column.
* Each column can load its next page independently when the user scrolls that column.
* Tasks inside a column are ordered by `updated_at DESC, id DESC`.
* Archived statuses are available only to the project owner and can be restored.
* A status with tasks cannot be archived until its tasks are moved to another active status.
* The last active status in a project cannot be archived.

### Technical requirements

* Use opaque cursor-based pagination; do not expose database offsets as cursors.
* The default and maximum page size is 500 tasks per column.
* Cursors must remain stable for the selected ordering and include a deterministic tie-breaker.
* Enforce all project and organization boundaries server-side.
* Status configuration mutations are owner-only; task moves are allowed to project members.
* Preserve `task.project_id == task.status.project_id` for every task write.
* Record history in the same transaction as a successful status change.
* Do not create a separate Kanban persistence entity.

## Acceptance Criteria

* [ ] A new project contains active `Backlog`, `In Progress`, and `Done` statuses in positions 0, 1, and 2.
* [ ] `GET /api/projects/{project_id}/board` returns `project_id` and ordered `columns`.
* [ ] Each board column contains the status representation, tasks, and its own `next_cursor`.
* [ ] The board returns at most 500 tasks per column.
* [ ] `GET /api/projects/{project_id}/board/columns/{status_id}/tasks` loads only the requested column.
* [ ] Column task pagination uses `limit` and opaque `cursor` query parameters.
* [ ] Repeated cursor requests do not duplicate or skip tasks under the documented ordering.
* [ ] Tasks are ordered by `updated_at DESC, id DESC`.
* [ ] A project member can move a task between active statuses in the same project.
* [ ] A user without project membership cannot read the board or move tasks.
* [ ] A cross-project status ID is rejected when moving a task.
* [ ] Every successful status move creates one history record with actor, timestamp, previous status, and new status.
* [ ] A no-op move to the current status does not create a transition record.
* [ ] `GET /api/tasks/{task_id}/history` returns newest events first with cursor pagination.
* [ ] Only the project owner can create, rename, reorder, archive, or restore statuses.
* [ ] Archiving a status with tasks is rejected until tasks are moved elsewhere.
* [ ] Archiving the last active status is rejected.
* [ ] Archived statuses do not appear in the normal status list or board columns.
* [ ] The project owner can list archived statuses from the archive endpoint.
* [ ] The project owner can restore an archived status.
* [ ] Existing authorization, task, membership, and ownership tests remain green.

## Domain

Relevant entities:

* `Project`
* `ProjectStatus`
* `Task`
* `TaskHistory` (new)

Relevant invariants:

* A project status belongs to exactly one project.
* A task status belongs to the same project as the task.
* At least one active status remains in every project.
* Archived statuses have no tasks because non-empty statuses cannot be archived.
* A task transition is attributable to one active project member.
* Status order is project-owned and is independent from task order within a column.

## Architecture

Affected areas:

* Backend models and Alembic migration for `TaskHistory` and default status initialization.
* Repository queries for board columns, cursor pagination, status archive, and history.
* Domain services for owner-only status configuration and member task moves.
* FastAPI routers and Pydantic board/history schemas.
* API documentation and authorization tests.

The request flow remains:

```text
HTTP request -> schema -> authentication -> authorization -> service -> repository -> database
```

## API

### Kanban board

```http
GET /api/projects/{project_id}/board
GET /api/projects/{project_id}/board/columns/{status_id}/tasks?limit=500&cursor=...
```

Board response:

```json
{
  "project_id": "project-uuid",
  "columns": [
    {
      "status": {
        "id": "status-uuid",
        "project_id": "project-uuid",
        "name": "Backlog",
        "position": 0,
        "is_active": true
      },
      "tasks": [],
      "next_cursor": "opaque-cursor-or-null"
    }
  ]
}
```

The column endpoint returns the same task page shape for one status and its `next_cursor`.

### Status configuration

Existing status routes remain, with owner-only authorization:

```http
POST  /api/projects/{project_id}/statuses
GET   /api/projects/{project_id}/statuses
PATCH /api/projects/{project_id}/statuses/{status_id}
POST  /api/projects/{project_id}/statuses/reorder
```

Add archive and restore operations:

```http
GET  /api/projects/{project_id}/statuses/archive
POST /api/projects/{project_id}/statuses/{status_id}/restore
```

Archiving is represented by `is_active = false`. If a dedicated `DELETE` route is used, it must perform the same soft-delete operation and rules.

### Task history

```http
GET /api/tasks/{task_id}/history?limit=500&cursor=...
```

History response entries contain:

```json
{
  "id": "history-uuid",
  "task_id": "task-uuid",
  "changed_by": "user-uuid",
  "from_status_id": "status-uuid",
  "to_status_id": "status-uuid",
  "created_at": "timestamp"
}
```

History is ordered by `created_at DESC, id DESC` and is visible to project members.

### Errors

* `401 Unauthorized` — missing or invalid bearer token.
* `403 Forbidden` — authenticated user is not a project member or is not the project owner for a configuration operation.
* `404 Not Found` — project, task, or status is not visible to the caller.
* `409 Conflict` — attempting to archive a non-empty/last active status or restore an invalid workflow state.
* `422 Unprocessable Entity` — invalid cursor, limit, status ID, or malformed request.

## Database

### Changes

* Add `task_history` with UUID primary key, task ID, actor user ID, previous status ID, next status ID, and `created_at`.
* Add explicit foreign keys with appropriate `ON DELETE` behavior.
* Add indexes for `(task_id, created_at DESC, id DESC)` and status/task lookup.
* Initialize default statuses for existing projects that have no statuses.
* Preserve existing project-specific status order and task/status constraints.

### Migration

A new Alembic migration is required:

* [x] Yes
* [ ] No

The migration must be safe for fresh databases and existing TASK-003 databases. Existing projects without statuses receive the three default statuses in the documented order.

## Authorization

* All board, status, task, and history endpoints require an active authenticated user.
* Board and history access require project membership and an active parent organization/project.
* Status create/update/reorder/archive/restore require `project.owner_id == current_user.id`.
* Task status moves require project membership.
* A task move must verify that the target status belongs to the task's project and is active.
* The backend must never trust a status ID without checking its project.

## Frontend

TASK-004 is backend/API work. The separate Kanban presentation is TASK-005.

The API must nevertheless expose stable contracts for TASK-005:

* ordered active columns;
* per-column task pages;
* per-column cursors;
* task history pages;
* predictable authorization and validation errors.

## Tests

### Backend

* [ ] Unit tests for cursor encoding/decoding and boundary conditions.
* [ ] API tests for board shape and status order.
* [ ] API tests for independent column pagination and 500-item limit.
* [ ] Authorization tests for member access and owner-only status configuration.
* [ ] Cross-project status rejection tests.
* [ ] Task transition history tests, including no-op moves.
* [ ] Archive/restore tests for non-empty and last-active statuses.
* [ ] Migration test for default statuses on existing projects.

### Frontend

* [ ] No frontend implementation required; TASK-005 consumes this API.

### Regression

* [ ] Registration, membership, ownership, task, and existing status tests remain green.

## Dependencies

* `TASK-001` — core task domain.
* `TASK-002` — authentication.
* `TASK-003` — project membership and authorization.
* `TASK-006` — containerized PostgreSQL development environment.

## Validation

```bash
# Backend
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app

# API/container smoke checks
cd ..
docker compose config
docker compose up -d --build
curl -fsS http://localhost:5173/health
```

## Definition of Done

* [ ] Requirements implemented.
* [ ] Acceptance criteria satisfied.
* [ ] Domain invariants preserved.
* [ ] Authorization implemented and tested.
* [ ] Database migration created and verified.
* [ ] API contract updated.
* [ ] Relevant tests added or updated.
* [ ] Relevant validation passed.
* [ ] Documentation updated.
* [ ] Final diff reviewed.
* [ ] No unrelated changes introduced.

## Implementation Notes

* Keep cursor payloads opaque to clients and versionable for future ordering changes.
* Use one deterministic ordering expression for both initial board pages and column continuation pages.
* Do not introduce a separate Kanban column table or hardcode status IDs in frontend/backend logic.
* If the history model becomes a general audit log later, that broader change belongs to a separate task.

## Status

* Status: TODO
* Started:
* Completed:

### Progress

* [ ] Analysis
* [ ] Implementation
* [ ] Tests
* [ ] Validation
* [ ] Review

### Known issues

* None
