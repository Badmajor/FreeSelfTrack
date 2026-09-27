# Development Status

## Current milestone

### MVP foundation

Goal:

Build the first complete vertical slice from organization to task.

---

## Tasks

| Task     | Description                       | Status |
| -------- | --------------------------------- | ------ |
| TASK-001 | Core task domain                  | TODO   |
| TASK-002 | Authentication                    | TODO   |
| TASK-003 | Project members and authorization | TODO   |
| TASK-004 | Kanban API                        | TODO   |
| TASK-005 | Kanban frontend                   | TODO   |

---

## Current focus

`TASK-001`

---

## Completed

None.

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

After `TASK-001`:

1. Authentication.
2. Project membership and authorization.
3. Kanban API.
4. Kanban frontend.
