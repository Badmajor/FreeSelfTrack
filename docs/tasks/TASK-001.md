# TASK-001: Core task domain

## Goal

Implement the initial backend domain required to create an organization, create a project, configure project statuses, and create tasks.

The result must provide the foundation for the Kanban board.

---

## Context

This is the first vertical slice of the product.

The MVP is based on project-owned workflows:

```text
Organization
    └── Project
          └── ProjectStatus
                └── Task
```

The project workflow must be defined by `ProjectStatus`.

There is no global status entity and no separate Kanban column entity.

---

## Requirements

### Organization

Implement the minimum organization entity required by the domain.

An organization:

* has an identifier;
* has a name;
* owns projects.

---

### Project

A project:

* belongs to exactly one organization;
* has an identifier;
* has a name;
* can contain tasks;
* owns its statuses.

---

### ProjectStatus

A `ProjectStatus`:

* belongs to exactly one project;
* has an identifier;
* has a name;
* has an order;
* may have an active/inactive state if required by the existing model;
* represents a task status;
* represents a Kanban column.

Status names must not be hardcoded.

Status order belongs to the project.

---

### Task

A task:

* belongs to exactly one project;
* has a title;
* references one `ProjectStatus`;
* references a task type when task types are implemented;
* may have a priority when priorities are implemented.

The task's status must belong to the same project as the task.

---

## Acceptance Criteria

### Organization

* [x] An organization can be persisted.
* [x] An organization can own multiple projects.
* [x] Project access is isolated by organization.

### Project

* [x] A project belongs to one organization.
* [x] A project can have multiple statuses.
* [x] Projects belonging to different organizations remain isolated.

### ProjectStatus

* [x] A project can have multiple statuses.
* [x] Status order is persisted.
* [x] Statuses belonging to different projects are isolated.
* [x] Status names are stored as project data rather than hardcoded application values.
* [x] The API returns statuses in project workflow order.

### Task

* [x] A task belongs to one project.
* [x] A task references a project status.
* [x] A task can be created using a status belonging to its project.
* [x] Creating a task with a status belonging to another project is rejected.
* [x] Retrieving a task enforces project/organization authorization.

### API

* [x] API endpoints use explicit Pydantic schemas.
* [x] API does not expose SQLAlchemy models directly.
* [x] Appropriate HTTP status codes are returned.
* [x] Validation errors are handled consistently.

### Database

* [x] SQLAlchemy models exist for the required entities.
* [x] Foreign keys enforce the required relationships.
* [x] Appropriate indexes and constraints exist.
* [x] Alembic migration creates the required schema.
* [x] The migration can be applied to an empty database.

### Tests

* [x] Organization creation is tested.
* [x] Project creation is tested.
* [x] Project status creation is tested.
* [x] Task creation is tested.
* [x] Cross-project status assignment is rejected.
* [x] Cross-organization/project access is rejected.
* [x] Relevant API validation errors are tested.

---

## Domain invariants

The following relationship is mandatory:

```text
Organization
  └── Project
        └── ProjectStatus
              └── Task
```

The following invariant must always hold:

```text
task.project_id == task.status.project_id
```

A task must never reference a status from another project.

A project must never expose statuses belonging to another project.

An organization must never expose projects belonging to another organization.

---

## Architecture

Use the existing modular monolith structure.

Expected backend flow:

```text
Router
  ↓
Schema
  ↓
Authorization
  ↓
Service
  ↓
Repository
  ↓
Database
```

Keep routers thin.

Business logic belongs in services.

Database access belongs in repositories.

---

## API

The exact endpoint structure should follow the existing API conventions in:

`docs/architecture/api.md`

At minimum, the implementation will require API operations for:

```text
Organization
    create

Project
    create
    retrieve

ProjectStatus
    create
    list
    update
    reorder

Task
    create
    retrieve
    update
```

Do not introduce endpoints that are not required by the current vertical slice.

---

## Authorization

All organization and project resources require authorization.

At minimum verify:

* authenticated user;
* organization access;
* project access;
* object-level access.

The implementation must protect against IDOR.

A user must not gain access to another organization's project by changing an ID in the request.

A task status from another project must not be accepted even if its ID is known.

---

## Database

Create the required SQLAlchemy models and Alembic migration.

The schema must represent:

```text
Organization
    1 ─── N
Project
    1 ─── N
ProjectStatus
    1 ─── N
Task
```

Use explicit foreign keys.

Use appropriate uniqueness constraints and indexes.

Do not create:

* global `Status`;
* `KanbanColumn`;
* global workflow tables.

---

## Frontend

Frontend implementation is not required for this task unless needed to verify the API.

The backend must expose enough information for a future Kanban implementation to derive columns from `ProjectStatus`.

The API must return project statuses in their persisted workflow order.

---

## Tests

At minimum implement tests for:

### Organization isolation

```text
User A -> Organization A -> Project A
User B -> Organization B -> Project B
```

User A must not access Project B.

### Project status isolation

```text
Project A
    └── Status A

Project B
    └── Status B
```

A task in Project A must not be allowed to use Status B.

### Workflow ordering

Create:

```text
Backlog
In Progress
Review
Done
```

Verify that the API returns them in the configured order.

### Task creation

Create a task using a status from the same project.

Verify successful creation.

### Invalid task status

Attempt to create a task using a status from another project.

Verify rejection.

---

## Dependencies

* None.

This is the first implementation task.

---

## Validation

Run the relevant backend checks configured by the repository.

Expected checks include:

```text
ruff check
ruff format --check
mypy
pytest
```

Use the actual project commands if they differ.

---

## Definition of Done

* [x] Organization model implemented.
* [x] Project model implemented.
* [x] ProjectStatus model implemented.
* [x] Task model implemented.
* [x] Relationships implemented.
* [x] Database constraints implemented.
* [x] Alembic migration created.
* [x] Repositories implemented.
* [x] Services implemented.
* [x] API endpoints implemented.
* [x] Authorization implemented.
* [x] Cross-project status protection implemented.
* [x] Tests implemented.
* [x] Relevant validation passes.
* [x] API documentation is consistent.
* [x] No global Status entity introduced.
* [x] No KanbanColumn entity introduced.
* [x] No unrelated refactoring introduced.

---

## Implementation Notes

The implementation should follow the existing repository structure and conventions.

Do not introduce task types, priorities, comments, watchers, attachments, notifications, search, or saved filters unless they are required by the existing code to make this vertical slice work.

Those features belong to later tasks.

If an architectural decision is required that changes the documented architecture, stop and record the decision before proceeding.

---

## Status

* Status: DONE
* Started: 2026-09-27
* Completed: 2026-09-27

### Progress

* [x] Analysis
* [x] Implementation
* [x] Tests
* [x] Validation
* [x] Review

### Known issues

* None
