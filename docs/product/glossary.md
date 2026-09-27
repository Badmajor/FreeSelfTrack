# Glossary

This document defines the canonical terminology used throughout the project.

AI agents, backend, frontend, tests, API documentation, and product documentation MUST use these terms consistently.

If a term has a specific definition here, do not introduce an alternative meaning without explicitly updating this document.

---

## General

### Organization

A top-level tenant and isolation boundary.

An organization contains users, teams, projects, and other organization-owned resources.

Resources belonging to one organization must not be accessible from another organization.

**Examples:**

* `Acme`
* `RideTrip`
* `My Company`

---

### User

An authenticated person who can interact with the system.

A user may belong to one or more organizations depending on the authorization model.

A user can participate in projects through project membership.

---

### Team

A group of users inside an organization.

Teams are used to organize people and may be used for project membership and authorization.

A team is not a project.

---

## Project Management

### Project

A workspace inside an organization where related tasks are managed.

A project owns its task workflow.

A project contains:

* project members;
* project statuses;
* task types;
* tasks;
* project-specific configuration.

A project is the primary boundary for task and workflow management.

---

### Project Member

A user or team membership granting access to a project.

Project membership determines which users can access and operate on project resources, subject to organization-level authorization.

---

### Project Role

A permission level assigned to a project member.

The exact set of roles is defined by the authorization model.

A role controls what a project member can do; it does not define the task workflow.

---

## Workflow

### Workflow

The ordered set of statuses belonging to a project.

In the MVP, a workflow is represented by the project's `ProjectStatus` records and their order.

There is no separate global workflow entity in the MVP.

---

### ProjectStatus

A status belonging to exactly one project.

`ProjectStatus` represents both:

1. a task status;
2. a Kanban column.

A project may have any number of statuses and may define its own status names and order.

Examples:

```text
Backlog
In Progress
Review
Done
```

Status names are project configuration and must not be hardcoded in application logic.

---

### Status Order

The position of a `ProjectStatus` within its project's workflow.

Status order determines the left-to-right order of Kanban columns.

Status order is shared by all users of the project.

---

### Task Status

The `ProjectStatus` currently assigned to a task.

A task status MUST belong to the same project as the task.

A task from Project A must never reference a status belonging to Project B.

---

### Status Transition

Changing a task from one `ProjectStatus` to another status within the same project.

A transition changes the task's current status.

The MVP does not contain a complex workflow engine or configurable transition graph.

Unless explicitly introduced later, a task can move between statuses belonging to its project.

---

## Tasks

### Task

A unit of work belonging to exactly one project.

A task has, at minimum:

* project;
* status;
* type;
* title;
* description;
* priority;
* creator;
* assignee;
* timestamps.

A task cannot exist outside a project.

---

### Task Type

A project-level classification of a task.

Examples:

```text
Task
Bug
Feature
Improvement
```

Task types are configurable and are not hardcoded into application logic.

---

### Priority

A task attribute describing its relative urgency or importance.

Priority is independent of status.

For example:

```text
Low
Normal
High
Critical
```

The exact priority model may be configurable.

---

### Assignee

The user currently responsible for completing a task.

A task may have no assignee.

An assignee must have access to the relevant project according to the authorization rules.

---

### Reporter

The user who created or reported a task.

Reporter and assignee are separate concepts.

---

### Task Ordering

The position of a task within a Kanban column/status.

Task ordering is independent from status ordering.

Moving a task between statuses may also change its position within the destination status.

---

## Kanban

### Kanban Board

The visual representation of a project's workflow.

A Kanban board is derived from the project's `ProjectStatus` records.

The board does not own an independent set of columns.

Conceptually:

```text
Project
  └── ProjectStatus
        ├── Task
        ├── Task
        └── Task
```

The Kanban board is a view of this data.

---

### Kanban Column

A visual column representing exactly one `ProjectStatus`.

There is no separate `KanbanColumn` domain entity in the MVP.

Column order is determined by `ProjectStatus` order.

Column names are the names of the corresponding project statuses.

---

### Column Width

A user-specific visual preference for the width of a Kanban column.

Column width does NOT change the project's workflow or status order.

Two users may see the same project with different column widths.

Example:

```text
Project A
├── Backlog       → 280px for User 1
├── In Progress   → 420px for User 1
└── Done          → 280px for User 1
```

Another user may have different widths for the same project.

---

### Board Settings

User-specific visual or interaction preferences for a project's Kanban board.

Examples may include:

* column widths;
* collapsed columns;
* visible task fields;
* other UI preferences.

Board settings must not change project-wide workflow semantics.

---

## Tags and Collaboration

### Tag

A label attached to a task for classification and filtering.

Tags are not task types and do not affect the task workflow.

A task may have multiple tags.

---

### Comment

A message attached to a task.

Comments are part of task collaboration and are separate from task history.

---

### Watcher

A user subscribed to updates for a task.

Watchers may receive notifications about relevant task changes.

Being a watcher does not imply being the assignee.

---

### Attachment

A file associated with a task or comment.

File metadata is stored in the application database while file contents may be stored in S3-compatible object storage.

---

## History and Notifications

### Task History

An immutable record of a significant task change.

Examples:

```text
Task status changed
Assignee changed
Priority changed
Title changed
Task created
```

History is intended to provide an audit trail of task changes.

History is not the same thing as comments.

---

### Notification

A system-generated message informing a user about an event relevant to them.

Examples:

```text
You were assigned a task.
A task you watch was updated.
Someone mentioned you in a comment.
```

Notifications are generated from domain events or application actions.

---

## Search and Filtering

### Filter

A set of criteria used to restrict the tasks displayed or returned by a query.

Examples:

```text
Status = In Progress
Assignee = Me
Priority = High
Tag = backend
```

Filters do not modify tasks.

---

### Saved Filter

A persisted filter definition that can be reused by a user.

A saved filter stores search criteria rather than a static list of tasks.

---

### Search

A query used to find tasks matching textual or structured criteria.

Search is read-only and must not modify task data.

---

## Authorization

### Authentication

The process of establishing who the user is.

Authentication answers:

> Who are you?

---

### Authorization

The process of determining whether an authenticated user is allowed to perform an operation.

Authorization answers:

> Are you allowed to do this?

Authentication and authorization are separate concerns.

---

### Organization Boundary

The security boundary separating resources belonging to different organizations.

An authenticated user must not be able to access another organization's resources by manipulating resource IDs.

---

### Project Boundary

The security boundary separating projects.

Project resources must be checked against the project to which the user has access.

---

### IDOR

Insecure Direct Object Reference.

A vulnerability where changing an object identifier allows a user to access an object they are not authorized to access.

Example:

```text
GET /api/tasks/123
GET /api/tasks/124
```

The fact that a user knows task `124` exists does not grant permission to access it.

Every object-level API operation must perform authorization checks.

---

## Architecture

### Modular Monolith

The application's backend architecture.

The system is deployed as one application but is internally divided into logical modules with clear responsibilities and boundaries.

The MVP is NOT a microservices architecture.

Modules should communicate through explicit application/service interfaces rather than through direct access to unrelated module internals.

---

### Router

The FastAPI HTTP layer responsible for:

* receiving requests;
* validating request schemas;
* invoking authorization;
* calling application services;
* returning response schemas.

Business logic should not live in routers.

---

### Schema

A Pydantic model used to define API input or output.

Schemas are part of the API contract and should not expose SQLAlchemy models directly.

---

### Service

An application/domain layer responsible for business logic and use cases.

Services coordinate repositories, authorization checks, transactions, and domain operations.

---

### Repository

A data-access layer responsible for persistence operations.

Repositories encapsulate database queries and should not contain unrelated business rules.

---

### Entity

A persistent domain object represented by a database record.

Examples:

```text
User
Organization
Project
ProjectStatus
Task
Comment
```

---

### DTO

Data Transfer Object.

A structured representation used to transfer data between application boundaries.

In the backend, Pydantic schemas commonly serve this purpose for API requests and responses.

---

## Database

### Migration

A versioned database schema change managed by Alembic.

Every database schema change must have an explicit migration.

Migrations must be safe to execute in the project's deployment environment.

---

### Seed Data

Initial or reference data inserted into the database by the application or deployment process.

Seed data must be deterministic and idempotent where appropriate.

---

## Files and Storage

### Object Storage

External storage for file contents.

The MVP uses S3-compatible storage such as MinIO.

The database stores metadata and references to stored files rather than large binary contents.

---

## Terminology Rules

The following terms must NOT be used interchangeably:

| Term           | Correct meaning                               | Do not confuse with      |
| -------------- | --------------------------------------------- | ------------------------ |
| Organization   | Top-level tenant                              | Project                  |
| Project        | Workspace containing tasks                    | Team                     |
| ProjectStatus  | Project-owned task status and Kanban column   | Global Status            |
| Workflow       | Ordered project statuses                      | KanbanBoard              |
| Kanban Board   | Visual representation of a project's workflow | ProjectStatus            |
| Kanban Column  | UI representation of one ProjectStatus        | Separate database entity |
| Task Status    | Current ProjectStatus of a task               | Task Type                |
| Task Type      | Classification of a task                      | Priority                 |
| Priority       | Importance/urgency attribute                  | Status                   |
| Assignee       | User responsible for task                     | Reporter                 |
| Reporter       | User who created/reported task                | Assignee                 |
| Comment        | User-written message                          | Task History             |
| Task History   | Audit record of changes                       | Comment                  |
| Watcher        | User subscribed to task updates               | Assignee                 |
| Filter         | Query criteria                                | Saved Filter             |
| Saved Filter   | Persisted reusable filter                     | Search result            |
| Authentication | Identifying the user                          | Authorization            |
| Authorization  | Checking permissions                          | Authentication           |
| Board Settings | User-specific UI preferences                  | Project configuration    |
| Column Width   | User-specific visual preference               | Status order             |

---

## Canonical Domain Relationships

The following relationships are fundamental to the MVP:

```text
Organization
├── Users
├── Teams
└── Projects
    ├── Project Members
    ├── Project Statuses
    │   └── Tasks
    ├── Task Types
    └── Tasks
        ├── Comments
        ├── Tags
        ├── Attachments
        ├── Watchers
        └── History
```

The critical workflow relationship is:

```text
Project
  └── ProjectStatus
        └── Task
```

Therefore:

```text
task.project_id == task.status.project_id
```

must always hold.

---

## Rules for AI Agents

AI agents MUST:

1. Read this glossary before introducing new domain terminology.
2. Use canonical terms in code, API documentation, tests, tasks, and UI descriptions.
3. Not introduce `Status` as a global entity when referring to `ProjectStatus`.
4. Not introduce a separate `KanbanColumn` entity for the MVP.
5. Treat a Kanban column as a visual representation of a `ProjectStatus`.
6. Keep project workflow configuration separate from user-specific board preferences.
7. Preserve the distinction between task status, task type, and priority.
8. Preserve the distinction between authentication and authorization.
9. Preserve organization and project security boundaries.
10. If a new domain concept cannot be accurately described using the existing terminology, propose an update to this glossary before implementing the concept.

When requirements conflict with this glossary, stop and resolve the terminology conflict before implementation.
