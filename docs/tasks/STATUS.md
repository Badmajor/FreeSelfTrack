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
| TASK-004 | Kanban API                        | DONE   |
| TASK-005 | Kanban frontend                   | DONE   |
| TASK-006 | Containerized self-hosted deployment | DONE   |
| TASK-007 | Task participants and in-app notifications | DONE   |
| TASK-008 | Frontend tests                   | DONE   |
| TASK-009 | Backend permission tests and Python 3.13 validation | DONE   |

---

## Current focus

`MVP foundation complete`

---

## Completed

* TASK-001 — Core task domain
* TASK-002 — Authentication.
* TASK-003 — Project members and authorization.
* TASK-006 — Containerized self-hosted deployment.
* TASK-004 — Kanban API and task workflow history.
* TASK-005 — Kanban frontend implementation.
* TASK-007 — Task participants and in-app notifications.
* TASK-008 — Frontend test suite.
* TASK-009 — Backend permission tests and Python 3.13 validation.

---

## In progress


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

Next milestone:

None.
