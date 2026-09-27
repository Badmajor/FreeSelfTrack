# ADR-002: Project-Owned Task Statuses

## Status

Accepted

## Date

2026-09-27

## Context

The product provides a Kanban-style task tracker.

Different projects may require different workflows.

For example:

```text
Software Project
    Backlog
    Development
    Code Review
    Testing
    Done
```

while another project may use:

```text
Marketing Project
    Ideas
    Planned
    In Progress
    Published
```

A global status catalog would impose unnecessary constraints on projects.

The Kanban board also needs a reliable source of truth for its columns.

---

## Decision

Each project owns its own `ProjectStatus` records.

```text
Project
    └── ProjectStatus
```

A `ProjectStatus` has:

* identifier;
* project identifier;
* name;
* workflow position;
* optional active/inactive state if required.

`ProjectStatus` has two domain meanings:

1. task status;
2. Kanban column.

---

## Core Invariant

Every task has exactly one current project status.

The following invariant must always hold:

```text
task.project_id == task.status.project_id
```

A task cannot reference a status belonging to another project.

---

## Workflow Ordering

Status order is stored as project data.

Example:

```text
Project A

0  Backlog
1  Development
2  Review
3  Done
```

The API returns statuses in this order.

The frontend uses the returned order when rendering Kanban columns.

---

## No Global Status Entity

The application must not introduce:

```text
Status
```

as a global domain entity.

There is no universal list such as:

```text
TODO
IN_PROGRESS
DONE
```

The names of statuses are project data.

---

## No Hardcoded Status IDs

The application must never depend on assumptions such as:

```python
if task.status_id == 1:
    ...
```

or:

```typescript
const DONE_STATUS_ID = 4;
```

Status identifiers are database data and may differ between projects and installations.

---

## Consequences

### Positive

* projects can define their own workflows;
* Kanban naturally follows project configuration;
* no duplicated workflow source of truth;
* fewer global assumptions;
* easier future workflow customization.

### Negative

* cross-project status validation is required;
* some application logic cannot assume universal statuses;
* reports must aggregate dynamically;
* frontend code must load statuses from the API.

---

## API Implications

Project statuses are exposed through project-scoped endpoints.

Example:

```http
GET /api/projects/{project_id}/statuses
```

Tasks are created and updated using a `status_id`.

The backend must verify that the referenced status belongs to the task's project.

---

## Database Implications

The database must represent:

```text
Project 1 ─── N ProjectStatus
ProjectStatus 1 ─── N Task
```

The implementation should use foreign keys, indexes, and service-level validation.

Where practical, database constraints should provide additional protection against invalid relationships.

---

## Rejected Alternatives

### Global Status

Rejected because projects may require different workflows.

### Separate Workflow Entity for MVP

Rejected because it adds another abstraction without a current product requirement.

A project's ordered `ProjectStatus` records are sufficient for the MVP.

### Hardcoded Status Enum

Rejected because it prevents project-specific workflows and makes the frontend dependent on application-level status names.
