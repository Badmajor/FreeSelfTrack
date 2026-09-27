# ADR-003: Kanban Columns Are Derived From ProjectStatus

## Status

Accepted

## Date

2026-09-27

## Context

The application contains a Kanban board.

A Kanban board visually represents task statuses as columns.

There are two possible approaches:

1. store statuses and Kanban columns as separate domain entities;
2. derive Kanban columns from project statuses.

The second approach avoids maintaining two representations of the same workflow.

---

## Decision

There is no separate `KanbanColumn` domain entity in the MVP.

Kanban columns are derived directly from ordered `ProjectStatus` records.

```text
ProjectStatus
      ↓
Kanban Column
```

Therefore:

```text
Kanban columns = ordered ProjectStatus records
```

---

## Example

Project configuration:

```text
ProjectStatus

0  Backlog
1  Development
2  Review
3  Done
```

The Kanban UI renders:

```text
┌──────────┬─────────────┬────────┬──────┐
│ Backlog  │ Development │ Review │ Done │
└──────────┴─────────────┴────────┴──────┘
```

No additional database records are required for these columns.

---

## Column Identity

A Kanban column is identified by its underlying `ProjectStatus.id`.

The frontend must not invent independent column identifiers.

---

## Column Order

Column order is determined by the project's status order.

Changing project status order changes Kanban column order.

The operation is therefore a workflow configuration operation rather than a UI-only operation.

---

## Column Width

Column width is **not** part of workflow configuration.

It is a presentation preference.

The same project may be displayed differently by different users.

Example:

```text
User A:
Backlog     = 240px
Development = 400px

User B:
Backlog     = 320px
Development = 280px
```

Column width must therefore not be stored on `ProjectStatus`.

If persisted, column-width preferences should be associated with the appropriate user/project context.

---

## Consequences

### Positive

* one source of truth;
* simpler database model;
* simpler API;
* no synchronization between statuses and columns;
* project workflow automatically drives Kanban;
* user UI preferences remain separate from domain workflow.

### Negative

* the frontend must dynamically render statuses;
* Kanban-specific behavior cannot assume fixed columns;
* future Kanban-only features may require additional presentation configuration.

---

## Frontend Rules

The frontend must:

1. fetch project statuses;
2. preserve server-provided order;
3. render one column per status;
4. group tasks by status;
5. use status IDs when moving tasks;
6. persist UI preferences separately from workflow configuration.

The frontend must not contain hardcoded columns.

Invalid:

```typescript
const columns = [
  "TODO",
  "IN_PROGRESS",
  "DONE",
];
```

Also invalid:

```typescript
if (status.id === "done") {
    ...
}
```

unless the identifier is explicitly part of a future documented domain contract.

---

## Backend Rules

The backend must expose enough information to construct the Kanban board from project statuses.

For example:

```http
GET /api/projects/{project_id}/statuses
```

returns ordered project statuses.

Task movement is implemented as a status change:

```http
PATCH /api/tasks/{task_id}
```

```json
{
  "status_id": "..."
}
```

There is no separate persistence operation such as:

```http
POST /api/kanban-columns/{column_id}/move
```

for the basic MVP.

---

## Rejected Alternative

### Separate KanbanColumn entity

Rejected because it duplicates the meaning already represented by `ProjectStatus`.

It would require synchronization between:

```text
ProjectStatus
```

and:

```text
KanbanColumn
```

and could create inconsistent states.

A separate entity may be reconsidered in the future if the product introduces genuinely independent Kanban concepts that cannot be represented as status presentation.

---

## Future Extension

If future requirements introduce board-specific presentation features, those features should initially be modeled as configuration/preferences around the project/status rather than immediately creating a second workflow entity.

Examples:

* column width;
* collapsed state;
* user-specific visibility;
* board-specific display options.

Such additions must not violate the principle that task workflow is owned by `ProjectStatus`.
