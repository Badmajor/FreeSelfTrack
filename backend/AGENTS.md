These instructions apply to all files under `backend/`.

The repository root `AGENTS.md` applies in addition to these instructions.

---

# Backend stack

- Python 3.13+
- FastAPI
- Pydantic 2.x
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Redis
- pytest
- Ruff
- mypy

Follow existing project conventions before introducing new patterns.

---

# Development environment

Use `uv` to manage the backend Python environment and dependencies.

Install `uv` with the official installer if it is not already available:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

From the `backend/` directory, create the virtual environment and install the
development dependencies:

```bash
uv venv
uv sync --extra dev
```

Run backend commands through `uv` so they use the project environment:

```bash
uv run uvicorn app.main:app --reload
uv run alembic upgrade head
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

The project requires Python 3.13 or newer. To select a specific installed
Python version when creating the environment, use `uv venv --python 3.13`.


---

# Backend structure

Expected responsibilities:

```text
app/
├── api/             HTTP endpoints and routing
├── schemas/         Pydantic request/response models
├── services/        application and domain logic
├── repositories/    database access
├── models/          SQLAlchemy models
├── dependencies/    FastAPI dependencies
├── db/              database configuration and sessions
└── core/            configuration and cross-cutting infrastructure
````

Keep these responsibilities separated.

Do not move business logic into routers simply because the logic is small.

---

# FastAPI

## Routers

Routers should be thin.

A router may:

* parse HTTP input;
* invoke dependencies;
* perform request-level validation;
* invoke authorization;
* call a service;
* map the result to a response schema;
* return the appropriate HTTP response.

A router should not:

* contain complex business rules;
* build large SQLAlchemy queries;
* perform unrelated database operations;
* implement workflow rules;
* duplicate service logic.

---

# Pydantic

Use Pydantic models for API boundaries.

Request and response schemas should be explicit.

Do not expose SQLAlchemy models directly from API endpoints.

Use appropriate validation constraints in schemas where validation belongs at the API boundary.

Do not rely on Pydantic validation as a replacement for business rules.

---

# Services

Services contain application and domain behavior.

A service should own operations such as:

* creating a project;
* creating or changing a task;
* changing task status;
* assigning a task;
* adding a comment;
* managing project configuration.

Services may coordinate:

* repositories;
* authorization checks;
* transactions;
* external services;
* background jobs.

Keep services focused on use cases rather than generic utility functions.

---

# Repositories

Repositories are responsible for persistence.

Repositories may:

* query models;
* create records;
* update records;
* delete records;
* load related data;
* apply persistence-specific filtering.

Repositories should not become a second service layer.

Do not place unrelated business rules in repositories.

Avoid leaking database implementation details into API schemas.

---

# SQLAlchemy

Use SQLAlchemy 2.x style APIs.

Prefer explicit typed queries.

For asynchronous code use the async SQLAlchemy APIs.

Avoid:

* implicit lazy loading in async request paths;
* N+1 queries;
* loading entire tables when pagination is appropriate;
* unnecessary database round trips.

Use eager loading deliberately when related data is required.

---

# Transactions

Transaction boundaries should correspond to meaningful application operations.

A service that performs multiple related database changes should normally execute them within one transaction when atomicity is required.

Do not commit from arbitrary repository methods unless the repository API explicitly requires that behavior.

Avoid partially completed domain operations.

---

# Domain workflow

The task workflow is project-owned.

```text
Project
  └── ProjectStatus
        └── Task
```

A `ProjectStatus` belongs to exactly one project.

A task belongs to exactly one project.

A task may reference only a `ProjectStatus` belonging to the same project.

The backend MUST enforce:

```text
task.project_id == task.status.project_id
```

Do not rely only on frontend validation for this invariant.

---

# ProjectStatus

`ProjectStatus` represents both:

1. the task status;
2. the Kanban column.

Do not introduce:

* a global status table;
* a separate `KanbanColumn` entity;
* hardcoded status IDs;
* hardcoded status names;
* hardcoded workflow order.

Status order belongs to the project workflow.

User-specific Kanban preferences, such as column width, must not modify project workflow data.

---

# Task operations

Task operations must validate:

* the task exists;
* the user can access the task;
* the task belongs to the expected project;
* referenced users have appropriate project access;
* referenced status belongs to the same project;
* referenced task type belongs to the appropriate project;
* requested state changes are valid.

When moving a task between statuses, preserve the project's workflow invariants.

---

# Authorization

Authorization is required at the backend boundary.

Do not trust:

* IDs supplied by the client;
* project IDs supplied by the client;
* organization IDs supplied by the client;
* frontend permission checks.

For object-level operations, verify access to the actual object.

Pay particular attention to IDOR vulnerabilities.

For example, retrieving:

```text
GET /api/tasks/{task_id}
```

must verify that the authenticated user is authorized to access that task.

Do not use "the user is authenticated" as a substitute for authorization.

---

# Database changes

Every schema change requires a new Alembic migration.

Do not edit migrations that may already have been applied.

Migration files must:

* have a clear purpose;
* preserve existing data where required;
* define appropriate foreign keys;
* define appropriate indexes and constraints;
* be reversible when practical.

When a migration requires data transformation, consider the existing production data and deployment order.

Database invariants should be enforced at the database level when practical.

---

# API design

Use REST conventions consistently.

For every endpoint define:

* request schema;
* response schema;
* authorization behavior;
* appropriate HTTP status codes;
* validation behavior;
* not-found behavior.

For collection endpoints, use server-side:

* pagination;
* filtering;
* sorting;

when the endpoint can return a potentially large dataset.

Do not return unbounded collections without a concrete reason.

---

# Errors

Use predictable API errors.

Do not expose:

* stack traces;
* SQL queries;
* credentials;
* tokens;
* internal secrets;
* sensitive user data.

Do not silently catch exceptions.

Avoid:

```python
except Exception:
    pass
```

Catch specific exceptions when recovery, translation, or cleanup is required.

---

# Redis

Redis may be used for:

* caching;
* rate limiting;
* ephemeral state;
* background-job coordination;
* other explicitly defined use cases.

Do not use Redis as the authoritative source of persistent domain data unless explicitly required by the architecture.

Cache invalidation must be considered whenever cached domain data changes.

---

# Background jobs

Long-running or asynchronous work must not block HTTP request handlers.

Use the project's configured background-job infrastructure when a task:

* is expensive;
* can run asynchronously;
* does not need to block the request;
* requires retries;
* requires scheduled execution.

Keep job handlers idempotent where practical.

---

# External services

External API calls must:

* have appropriate timeouts;
* handle expected failures;
* avoid leaking secrets;
* provide useful logging;
* avoid blocking the event loop.

Do not make external network calls directly from database repositories.

---

# Async code

Backend request handling is asynchronous.

Do not perform blocking I/O in async request paths.

Be especially careful with:

* filesystem operations;
* synchronous HTTP clients;
* synchronous database access;
* CPU-heavy operations.

Move expensive CPU-bound work to an appropriate background mechanism when necessary.

---

# Testing

Backend behavior must be covered by tests appropriate to the change.

Prefer:

* unit tests for isolated business logic;
* integration tests for database behavior;
* API tests for HTTP contracts;
* regression tests for previously discovered bugs.

For authorization-sensitive operations test:

* authorized access;
* unauthorized access;
* cross-organization access;
* cross-project access;
* object ID manipulation.

For workflow operations test:

* valid status changes;
* invalid status references;
* cross-project status references;
* status ordering;
* task/project consistency.

---

# Validation

For backend changes, run the relevant checks.

Typical checks include:

```text
ruff check
ruff format --check
mypy
pytest
```

Use the project's actual configured commands from `pyproject.toml`, `Makefile`, or development documentation.

Do not claim validation passed if the relevant command was not actually run.

---

# Backend completion checklist

Before considering a backend task complete, verify:

* [ ] Router remains thin.
* [ ] Business logic is in the appropriate service.
* [ ] Database access is isolated appropriately.
* [ ] Authorization is enforced.
* [ ] Organization/project boundaries are preserved.
* [ ] ProjectStatus/task relationship is valid.
* [ ] Migration exists when schema changed.
* [ ] API schemas are explicit.
* [ ] Relevant tests exist.
* [ ] Relevant validation was run.
* [ ] No debug code or secrets remain.

[2]: https://developers.openai.com/api/docs/guides/tools-skills?utm_source=chatgpt.com "Skills | OpenAI API"
[3]: https://developers.openai.com/blog/run-long-horizon-tasks-with-codex?utm_source=chatgpt.com "Run long horizon tasks with Codex | OpenAI Developers"
