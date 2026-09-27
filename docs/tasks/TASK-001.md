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

* [ ] An organization can be persisted.
* [ ] An organization can own multiple projects.
* [ ] Project access is isolated by organization.

### Project

* [ ] A project belongs to one organization.
* [ ] A project can have multiple statuses.
* [ ] Projects belonging to different organizations remain isolated.

### ProjectStatus

* [ ] A project can have multiple statuses.
* [ ] Status order is persisted.
* [ ] Statuses belonging to different projects are isolated.
* [ ] Status names are stored as project data rather than hardcoded application values.
* [ ] The API returns statuses in project workflow order.

### Task

* [ ] A task belongs to one project.
* [ ] A task references a project status.
* [ ] A task can be created using a status belonging to its project.
* [ ] Creating a task with a status belonging to another project is rejected.
* [ ] Retrieving a task enforces project/organization authorization.

### API

* [ ] API endpoints use explicit Pydantic schemas.
* [ ] API does not expose SQLAlchemy models directly.
* [ ] Appropriate HTTP status codes are returned.
* [ ] Validation errors are handled consistently.

### Database

* [ ] SQLAlchemy models exist for the required entities.
* [ ] Foreign keys enforce the required relationships.
* [ ] Appropriate indexes and constraints exist.
* [ ] Alembic migration creates the required schema.
* [ ] The migration can be applied to an empty database.

### Tests

* [ ] Organization creation is tested.
* [ ] Project creation is tested.
* [ ] Project status creation is tested.
* [ ] Task creation is tested.
* [ ] Cross-project status assignment is rejected.
* [ ] Cross-organization/project access is rejected.
* [ ] Relevant API validation errors are tested.

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

* [ ] Organization model implemented.
* [ ] Project model implemented.
* [ ] ProjectStatus model implemented.
* [ ] Task model implemented.
* [ ] Relationships implemented.
* [ ] Database constraints implemented.
* [ ] Alembic migration created.
* [ ] Repositories implemented.
* [ ] Services implemented.
* [ ] API endpoints implemented.
* [ ] Authorization implemented.
* [ ] Cross-project status protection implemented.
* [ ] Tests implemented.
* [ ] Relevant validation passes.
* [ ] API documentation is consistent.
* [ ] No global Status entity introduced.
* [ ] No KanbanColumn entity introduced.
* [ ] No unrelated refactoring introduced.

---

## Implementation Notes

The implementation should follow the existing repository structure and conventions.

Do not introduce task types, priorities, comments, watchers, attachments, notifications, search, or saved filters unless they are required by the existing code to make this vertical slice work.

Those features belong to later tasks.

If an architectural decision is required that changes the documented architecture, stop and record the decision before proceeding.

---

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
