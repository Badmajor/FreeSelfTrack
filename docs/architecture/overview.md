# Architecture Overview

## 1. Architecture Style

The application is a **modular monolith**.

Backend modules are deployed as one application but have explicit domain boundaries.

The architecture should allow future extraction of modules into services if there is a demonstrated need, but the MVP must not introduce microservice complexity without a concrete requirement.

```text
                    ┌──────────────────────┐
                    │      Frontend        │
                    │ React + TypeScript   │
                    └──────────┬───────────┘
                               │
                               │ HTTP/REST
                               ▼
                    ┌──────────────────────┐
                    │       FastAPI        │
                    │   Modular Monolith   │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        PostgreSQL           Redis        Object Storage
                                      S3-compatible / MinIO
```

---

# 2. Backend Stack

The backend uses:

* Python 3.13+;
* FastAPI;
* Pydantic 2.x;
* SQLAlchemy 2.x;
* Alembic;
* PostgreSQL;
* Redis;
* pytest;
* Ruff;
* mypy.

Optional infrastructure components may be added only when required by the product.

---

# 3. Frontend Stack

The frontend uses:

* TypeScript;
* React;
* Vite;
* React Router;
* TanStack Query;
* ESLint.

The frontend communicates with the backend through the REST API.

The backend OpenAPI specification is the source of truth for API contracts.

---

# 4. Backend Module Boundaries

The backend should be organized by responsibility/domain rather than by one large collection of unrelated endpoints.

Expected conceptual modules:

```text
app/
├── core/
├── db/
├── api/
├── dependencies/
├── models/
├── schemas/
├── repositories/
└── services/
```

As the domain grows, module-specific organization may be introduced where it improves boundaries.

Example:

```text
projects/
    models.py
    schemas.py
    repository.py
    service.py
    router.py
```

The chosen organization must remain consistent.

Do not mix two architectural patterns without a concrete reason.

---

# 5. Layer Responsibilities

The standard backend flow is:

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

## Router

Responsible for:

* HTTP routing;
* dependency injection;
* request/response schemas;
* HTTP status codes;
* translating known domain errors into HTTP responses.

Routers should remain thin.

---

## Schema

Pydantic schemas define external API contracts.

Schemas must not expose SQLAlchemy models directly.

Input schemas and output schemas should be separated where necessary.

---

## Authorization

Authorization verifies:

* authenticated user;
* organization membership;
* project membership;
* required role;
* object ownership/access.

Authorization must be performed server-side.

---

## Service

Services contain business rules.

Examples:

```text
create_project()
create_project_status()
reorder_project_statuses()
create_task()
move_task()
```

Services enforce domain invariants.

---

## Repository

Repositories encapsulate database access.

Repositories should contain:

* SQLAlchemy queries;
* persistence operations;
* database-specific loading strategies.

Repositories should not become the primary location for business policy.

---

# 6. Domain Ownership

The central relationship is:

```text
Organization
    └── Project
          └── ProjectStatus
                └── Task
```

Project owns workflow.

`ProjectStatus` represents both:

* task status;
* Kanban column.

There is no separate `KanbanColumn` entity.

---

# 7. Project Status Architecture

A project's statuses are stored in PostgreSQL.

Example:

```text
Project 42

ProjectStatus
-----------------------------
id | name        | position
-----------------------------
1  | Backlog     | 0
2  | Development | 1
3  | Review      | 2
4  | Done        | 3
```

The frontend retrieves this data from the API.

Kanban columns are derived from these records:

```text
ProjectStatus ordered by position
            ↓
        Kanban columns
```

There must be one source of truth.

---

# 8. Status Integrity

The backend must enforce:

```text
task.project_id == task.status.project_id
```

Do not rely exclusively on frontend validation.

A request such as:

```json
{
  "project_id": 10,
  "status_id": 999
}
```

must be rejected if status `999` belongs to another project.

The service layer must verify the relationship.

Database constraints should provide additional protection where practical.

---

# 9. Task Lifecycle

A task belongs to a project and has one current status.

Conceptually:

```text
Task
├── project
├── status
├── reporter
├── assignee
├── type
├── priority
└── metadata
```

Changing the task status is a domain operation.

It must not permit assigning a status from another project.

---

# 10. Database

PostgreSQL is the primary relational database.

Use:

* UUID or another consistent non-guessable identifier strategy;
* foreign keys;
* unique constraints;
* indexes;
* transactions;
* explicit migrations.

The exact identifier strategy must be selected once and applied consistently.

---

# 11. Transactions

Business operations that modify multiple related records must use a transaction.

Examples:

```text
Create project
    + create default statuses
```

or:

```text
Reorder statuses
    + update multiple positions
```

The operation must either complete successfully or roll back.

---

# 12. Alembic

All schema changes must be represented by Alembic migrations.

Do not modify the database schema manually in development and leave migrations out of the repository.

Migrations must be:

* deterministic;
* reviewable;
* reversible where practical;
* applicable to an empty database.

---

# 13. Redis

Redis is an infrastructure dependency for functionality such as:

* caching;
* rate limiting;
* temporary state;
* notification queues;
* background-job coordination.

Redis must not become the source of truth for persistent domain data.

PostgreSQL remains authoritative for business entities.

---

# 14. Object Storage

File contents are stored in S3-compatible object storage.

The database stores metadata such as:

```text
Attachment
├── id
├── task_id
├── filename
├── content_type
├── size
└── object_key
```

The binary file itself is stored in object storage.

For local/self-hosted development, MinIO is the default implementation.

---

# 15. Background Jobs

Long-running or asynchronous work must not block normal HTTP requests.

Potential background jobs include:

* notification delivery;
* file processing;
* expensive statistics;
* future email delivery;
* maintenance jobs.

The MVP should keep the background-job mechanism as simple as possible.

Do not introduce a message broker unless an actual requirement justifies it.

---

# 16. Authentication

Authentication is responsible for identifying the current user.

Authorization is a separate layer.

The architecture must not treat:

```text
authenticated
```

as equivalent to:

```text
authorized for this resource
```

Every protected resource must perform appropriate authorization checks.

---

# 17. Organization Boundary

Organization is the primary tenant boundary.

Every organization-scoped resource must ultimately resolve to an organization.

For example:

```text
Task
  ↓
Project
  ↓
Organization
```

An authenticated user must not be able to retrieve a task merely because the task ID is known.

---

# 18. Project Boundary

Project-scoped resources must be checked against the project.

Examples:

* tasks;
* statuses;
* tags;
* comments;
* attachments.

A resource must not cross project boundaries accidentally.

---

# 19. IDOR Protection

The backend must assume that clients can manipulate every identifier.

For example:

```http
GET /api/projects/123
```

does not imply that project `123` may be returned.

The service must verify that the authenticated user has access.

The same principle applies to:

* task IDs;
* status IDs;
* comment IDs;
* attachment IDs;
* saved filter IDs.

---

# 20. API Data Flow

Typical request:

```text
HTTP request
     ↓
FastAPI router
     ↓
Request schema validation
     ↓
Authentication
     ↓
Authorization
     ↓
Service
     ↓
Repository
     ↓
SQLAlchemy
     ↓
PostgreSQL
     ↓
Repository
     ↓
Service
     ↓
Response schema
     ↓
HTTP response
```

---

# 21. Error Handling

API errors must use consistent response structures.

Expected categories include:

```text
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
422 Validation Error
```

Do not expose internal stack traces or database implementation details to API clients.

Domain errors should be translated into appropriate HTTP responses.

---

# 22. Frontend Architecture

The frontend should be organized around product features rather than one giant component tree.

Example:

```text
src/
├── app/
├── pages/
├── features/
│   ├── auth/
│   ├── projects/
│   ├── tasks/
│   ├── kanban/
│   └── notifications/
├── components/
├── api/
├── hooks/
├── lib/
└── types/
```

The exact structure may evolve as implementation progresses.

---

# 23. Frontend State

TanStack Query should manage server state.

Local React state should manage UI state.

Do not duplicate the complete server-side domain state in a global frontend store without a concrete reason.

---

# 24. Kanban Frontend

The Kanban board must:

1. request project statuses from the API;
2. preserve their server-provided order;
3. render one column per status;
4. load tasks associated with the project;
5. group tasks by status;
6. support moving tasks between valid statuses.

The frontend must not contain logic such as:

```typescript
if (status.id === 1) ...
```

or:

```typescript
const columns = ["TODO", "IN_PROGRESS", "DONE"];
```

Workflow configuration comes from the backend.

---

# 25. API Contract

The backend OpenAPI specification is the canonical API contract.

Frontend API clients should be generated or implemented from the API contract rather than manually maintaining duplicated assumptions.

When the API changes:

1. update backend schemas;
2. update API implementation;
3. update generated/client types if applicable;
4. update frontend consumers;
5. update tests.

---

# 26. Testing Architecture

Testing should exist at several levels.

### Unit tests

Test isolated domain/service behavior where useful.

### Integration tests

Test:

* database interactions;
* authorization;
* repository behavior;
* API endpoints.

### End-to-end tests

Use only where the user flow justifies the additional complexity.

The MVP should prioritize reliable backend integration tests and focused frontend tests.

---

# 27. Observability

The application should provide structured logs for important operations.

Logs should include useful identifiers where appropriate:

```text
request_id
user_id
organization_id
project_id
task_id
```

Do not log:

* passwords;
* tokens;
* secrets;
* sensitive file contents.

Metrics and tracing can be expanded after the core MVP.

---

# 28. Deployment

The default self-hosted deployment target is Docker Compose.

Conceptually:

```text
docker compose
├── frontend
├── backend
├── postgres
├── redis
└── minio
```

The exact production topology may evolve independently from the application architecture.

---

# 29. Dependency Policy

New production dependencies should only be introduced when they solve a concrete requirement.

Before adding a dependency:

1. check whether existing dependencies already solve the problem;
2. consider maintenance cost;
3. consider self-hosted deployment impact;
4. consider security implications;
5. document significant architectural choices.

---

# 30. Architecture Decision Boundary

If implementation requires changing a documented architectural principle, do not silently make the change.

Create or update an ADR in:

```text
docs/architecture/decisions/
```

The ADR should explain:

* context;
* decision;
* alternatives;
* consequences.
