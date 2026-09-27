# Product Requirements

## 1. Product

A free, self-hosted task tracker for small and medium-sized teams.

The product is intended to provide the core functionality of a modern issue tracker without requiring a hosted SaaS subscription.

The initial product is inspired by tools such as Yandex Tracker, Linear, Jira, and similar task-management systems, but the implementation must remain intentionally smaller and focused.

---

## 2. Product Goals

The MVP must allow a team to:

1. create an organization;
2. create projects;
3. invite/manage project members;
4. configure project-specific task statuses;
5. create and manage tasks;
6. use a Kanban board based on project statuses;
7. comment on tasks;
8. track task history;
9. watch tasks;
10. attach files;
11. tag tasks;
12. search and filter tasks;
13. save frequently used filters;
14. receive basic notifications;
15. view basic project/task statistics.

The system must be suitable for self-hosting with Docker Compose.

---

## 3. Product Principles

### 3.1 Self-hosted first

The product must be usable without a proprietary hosted backend.

Core functionality must work entirely inside the user's infrastructure.

External SaaS dependencies must not be required for the MVP.

---

### 3.2 Project-owned workflow

Every project owns its own workflow.

A project's workflow consists of `ProjectStatus` records.

A `ProjectStatus` is simultaneously:

* a task status;
* a Kanban column.

There is no global status catalog.

There is no separate `KanbanColumn` domain entity.

---

### 3.3 Configurable projects

Projects must not depend on hardcoded application-level status IDs or names.

For example, the application must not assume that every project contains:

```text
TODO
IN_PROGRESS
DONE
```

A project may instead define:

```text
Backlog
Analysis
Development
Review
Testing
Released
```

Another project may use completely different statuses.

---

### 3.4 Backend as source of truth

The backend owns:

* authorization;
* organization boundaries;
* project boundaries;
* workflow rules;
* task state;
* data validation;
* persistence.

The frontend must not implement business rules that can be bypassed by direct API requests.

---

## 4. Users and Organizations

### Organization

An organization is the top-level tenant.

An organization contains:

* users/members;
* teams;
* projects.

A user may belong to multiple organizations.

Organization data must be isolated from other organizations.

---

### User

A user represents an authenticated account.

A user may:

* belong to organizations;
* participate in projects;
* create tasks;
* update tasks according to permissions;
* comment;
* watch tasks.

Authentication and authorization are separate concerns.

---

### Team

A team groups users for organizational purposes.

Teams are part of the MVP domain but do not need to own workflows.

A project may later use teams for assignment and access management.

---

## 5. Projects

A project belongs to exactly one organization.

A project contains:

* members;
* statuses;
* tasks;
* tags;
* project configuration.

A project owns its workflow.

Projects from different organizations must never expose each other's data.

---

## 6. Tasks

A task belongs to exactly one project.

A task contains at minimum:

* identifier;
* title;
* description;
* status;
* creator/reporter;
* assignee;
* creation timestamp;
* update timestamp.

Additional MVP task data:

* task type;
* priority;
* tags;
* comments;
* attachments;
* watchers;
* history.

---

## 7. Task Types

Projects may use configurable task types.

Examples:

```text
Task
Bug
Feature
Improvement
Question
```

Task type names and identifiers must not be hardcoded into frontend logic.

---

## 8. Priorities

Tasks may have a priority.

The initial implementation may use a predefined priority set if required by the implementation.

Priority behavior must remain independent from project status.

Example:

```text
Low
Normal
High
Critical
```

Priority must not determine Kanban column placement.

---

## 9. Kanban

The Kanban board is derived from project statuses.

Example:

```text
ProjectStatus
├── Backlog
├── In Progress
├── Review
└── Done
```

The frontend renders these statuses as columns.

Column order is determined by the project's `ProjectStatus` order.

The board must dynamically load the statuses from the API.

The frontend must never assume a fixed number of columns.

---

## 10. Kanban Column Preferences

Column width is a presentation preference.

It is not part of the project's workflow definition.

Column width may be stored as a user-specific preference.

Example:

```text
User A:
Backlog     = 280px
In Progress = 400px

User B:
Backlog     = 220px
In Progress = 300px
```

Changing column width must not modify project workflow.

---

## 11. Comments

Users can comment on tasks.

Comments belong to a task.

The MVP should support:

* creation;
* retrieval;
* basic editing if required;
* basic deletion if required by authorization rules.

Comment operations must respect task/project authorization.

---

## 12. Task History

Important task changes should be recorded in history.

Examples:

* status changed;
* assignee changed;
* priority changed;
* title changed;
* task created;
* task deleted.

History is append-oriented and should provide enough information to understand what changed.

---

## 13. Watchers

Users can watch tasks.

A watcher receives notifications about relevant task changes.

Users should be able to:

* subscribe;
* unsubscribe;
* list watchers.

---

## 14. Attachments

Tasks may contain file attachments.

The application must use S3-compatible object storage for files.

The database stores attachment metadata.

The object storage contains file contents.

The MVP should support MinIO for local/self-hosted deployments.

---

## 15. Tags

Tasks may have multiple tags.

Tags belong to a project.

A tag from one project must not be attachable to a task belonging to another project.

---

## 16. Search and Filters

Users must be able to find tasks using:

* text;
* status;
* assignee;
* reporter;
* task type;
* priority;
* tags.

Filtering must respect organization and project authorization.

The initial implementation does not require a full YQL-compatible query language.

---

## 17. Saved Filters

Users can save frequently used task filters.

A saved filter belongs to a user and is associated with a project or organization context.

The saved filter stores structured filter configuration rather than arbitrary executable SQL.

---

## 18. Notifications

The MVP supports basic notifications.

Examples:

* task assigned to user;
* user mentioned in a comment;
* watched task changed;
* task status changed.

The initial implementation may use in-app notifications.

Email notifications are optional and should not block the MVP.

---

## 19. Dashboard

The MVP dashboard provides basic project/task information.

Possible metrics:

* total tasks;
* tasks by status;
* tasks by assignee;
* recently updated tasks;
* overdue tasks if due dates are implemented.

The dashboard must derive status information from the project's configured workflow.

---

# 20. Authentication

Authentication is required for protected application functionality.

The implementation may use:

* access tokens;
* refresh tokens;
* secure cookies or authorization headers.

The exact mechanism is defined by the backend architecture.

Authentication answers:

> Who is this user?

Authorization answers:

> What may this user access?

---

# 21. Authorization

Authorization must be enforced on the backend.

The MVP must protect:

* organization access;
* project access;
* project membership;
* task access;
* comments;
* attachments;
* tags;
* saved filters.

The application must protect against IDOR.

Changing a resource ID in an API request must never allow access to an unauthorized resource.

---

# 22. MVP Scope

## Included

```text
Authentication
Organizations
Users
Teams
Projects
Project members
Project roles
Project statuses
Task types
Tasks
Priorities
Kanban
Comments
Task history
Watchers
Attachments
Tags
Search
Filters
Saved filters
Notifications
Dashboard
REST API
OpenAPI
Docker Compose
PostgreSQL
Redis
S3-compatible storage
Automated tests
CI
```

---

# 23. Explicitly Out of MVP

The following are intentionally excluded from the initial MVP:

* Scrum sprints;
* complex workflow engine;
* conditional workflow transitions;
* Gantt charts;
* advanced time tracking;
* SLA management;
* LDAP;
* enterprise SSO;
* mobile applications;
* marketplace;
* large integration catalog;
* AI assistant;
* full YQL implementation;
* arbitrary custom fields;
* arbitrary per-project automation engine.

These may be considered after the MVP.

---

# 24. Core Domain Invariants

The following invariants must always hold.

### Organization isolation

```text
Project.organization_id
    belongs to
Organization
```

A project cannot belong to multiple organizations.

---

### Project workflow ownership

```text
Project
    └── ProjectStatus
```

A status belongs to exactly one project.

---

### Task status integrity

```text
Task.project_id == Task.status.project_id
```

A task must never reference a status belonging to another project.

---

### Kanban derivation

```text
Kanban columns = ordered ProjectStatus records
```

The application must not maintain a second source of truth for Kanban columns.

---

### Project isolation

Every project-scoped entity must be reachable through an authorized project.

---

# 25. Primary User Flows

## Create project

```text
User
  ↓
Organization
  ↓
Create Project
  ↓
Create default ProjectStatus records
  ↓
Project becomes ready for tasks
```

Default statuses may be introduced during project creation, but their names and ordering must remain project data after creation.

---

## Create task

```text
User
  ↓
Project
  ↓
Select ProjectStatus
  ↓
Create Task
```

The backend verifies that the selected status belongs to the selected project.

---

## Open Kanban

```text
User
  ↓
Project
  ↓
Load ProjectStatus ordered by workflow order
  ↓
Load tasks grouped by status
  ↓
Render columns dynamically
```

---

# 26. Success Criteria

The MVP is considered functionally successful when a self-hosted installation allows a team to:

1. create an organization;
2. create a project;
3. configure statuses;
4. create tasks;
5. move tasks between project statuses;
6. view those statuses as Kanban columns;
7. collaborate through comments;
8. inspect task history;
9. search and filter tasks;
10. use the system without relying on a hosted SaaS backend.

Technical success additionally requires:

* reproducible Docker deployment;
* database migrations;
* automated tests;
* documented API;
* documented setup;
* clear authorization boundaries.
