# Development Status

## Current milestone

### MVP foundation

Goal:

Build the first complete vertical slice from organization to task.

---

## Tasks

| Task     | Description                       | Status |
| -------- | --------------------------------- | ------ |
| TASK-001 | Core task domain                  | DONE   |
| TASK-002 | Authentication                    | DONE   |
| TASK-003 | Project members and authorization | DONE   |
| TASK-004 | Kanban API                        | TODO   |
| TASK-005 | Kanban frontend                   | TODO   |
| TASK-006 | Containerized self-hosted deployment | DONE   |

---

## Current focus

`TASK-004`

---

## Completed

* TASK-001 — Core task domain
* TASK-002 — Authentication.
* TASK-003 — Project members and authorization.
* TASK-006 — Containerized self-hosted deployment.

---

## In progress

None.

---

## Blocked

None.

---

## Architectural decisions

Current important decisions:

* Modular monolith.
* Project-owned workflow.
* `ProjectStatus` is both task status and Kanban column.
* No global Status entity.
* No separate KanbanColumn entity.
* Kanban column width is a user-specific preference.

See:

`docs/architecture/decisions/`

---

## Known issues

None.

---

## Next milestone

After `TASK-003`:

1. Kanban API.
2. Kanban frontend.
