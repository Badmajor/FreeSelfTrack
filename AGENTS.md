# AGENTS.md

## Project

This repository contains a free, self-hosted task tracker for teams.

The application is a modular monolith.

The product is inspired by modern issue trackers such as Yandex Tracker, but it is an independent implementation.

---

## How to use project documentation

Do not read the entire documentation tree before every task.

Read the documents relevant to the current task.

### Product

* `docs/product/requirements.md` — product requirements and MVP scope.
* `docs/product/glossary.md` — canonical product and domain terminology.
* `docs/product/roadmap.md` — planned product development.

### Architecture

* `docs/architecture/overview.md` — system architecture and module boundaries.
* `docs/architecture/api.md` — API conventions and contracts.
* `docs/architecture/decisions/` — accepted architectural decisions and their rationale.

### Development

* `docs/development/setup.md` — local development setup.
* `docs/development/testing.md` — testing strategy and commands.

### Tasks

* `docs/tasks/TEMPLATE.md` — task format.
* `docs/tasks/TASK-*.md` — concrete implementation tasks.

When a task references a document, read that document before making implementation decisions based on it.

When a domain concept is unclear, check `docs/product/glossary.md`.

When an architectural decision is unclear, check the relevant document in `docs/architecture/decisions/`.

---

# Core principles

## 1. Preserve the domain model

Do not introduce new entities, relationships, or abstractions without a concrete requirement.

Prefer the simplest model that satisfies the current requirements.

Do not implement speculative functionality.

---

## 2. Project-owned workflow

The task workflow belongs to the project.

The canonical relationship is:

```text
Project
  └── ProjectStatus
        └── Task
```

`ProjectStatus` represents both:

* the status of a task;
* a Kanban column.

There is no separate global `Status` entity in the MVP.

There is no separate `KanbanColumn` domain entity in the MVP.

A project may have its own statuses and status order.

Status names, IDs, number of statuses, and workflow order must never be hardcoded.

A task status MUST belong to the same project as the task.

The following invariant must always hold:

```text
task.project_id == task.status.project_id
```

---

## 3. Kanban

The Kanban board is a visual representation of a project's workflow.

Kanban columns are derived from the project's `ProjectStatus` records.

Column order is determined by project status order.

Column width is a user-specific visual preference.

Changing column width must not change:

* project workflow;
* status order;
* task status;
* project configuration.

User-specific board preferences must not become project-wide workflow configuration.

---

## 4. Backend is the source of truth

The backend owns:

* domain rules;
* authorization;
* validation;
* workflow integrity;
* persistence;
* API contracts.

The frontend must not independently implement domain rules that belong to the backend.

Frontend validation may improve UX, but must not replace backend validation.

---

# Architecture

The backend is a modular monolith.

Keep application responsibilities separated:

```text
HTTP Request
    ↓
Router
    ↓
Schema validation
    ↓
Authorization
    ↓
Service
    ↓
Repository
    ↓
Database
```

### Router

Routers handle HTTP concerns:

* request parsing;
* dependency injection;
* authorization invocation;
* service invocation;
* response serialization;
* HTTP status codes.

Business logic must not be placed in routers.

### Schema

Pydantic schemas define API input and output.

Do not expose SQLAlchemy models directly from API endpoints.

### Service

Services contain application and domain logic.

Services coordinate:

* business rules;
* authorization;
* repositories;
* transactions;
* external services.

### Repository

Repositories contain database access logic.

Do not scatter SQLAlchemy queries throughout routers and unrelated services.

---

# Security and authorization

Authentication and authorization are separate concerns.

Authentication answers:

> Who is the user?

Authorization answers:

> Is this user allowed to perform this operation?

Always enforce resource boundaries.

## Organization boundary

A user must not access resources belonging to another organization.

## Project boundary

A user must have appropriate project access before accessing project resources.

## Object-level authorization

Never assume that possession of an object ID grants access.

Every object-level operation must verify authorization.

Protect against IDOR vulnerabilities.

For example:

```text
GET /api/tasks/123
```

must verify that the authenticated user can access task `123`.

Do not rely on the frontend to enforce authorization.

---

# Database

PostgreSQL is the primary database.

SQLAlchemy 2.x is used for ORM and database access.

Alembic is used for schema migrations.

## Database rules

* Every schema change requires an Alembic migration.
* Do not modify an existing migration that may already have been applied.
* Define explicit foreign-key behavior.
* Use database constraints to protect important invariants where practical.
* Add indexes based on actual query patterns.
* Avoid N+1 queries.
* Keep transaction boundaries explicit.
* Do not perform blocking database operations in async request handlers.

When changing the database schema, read the relevant database and architecture documentation before implementation.

---

# API

FastAPI is used for the REST API.

API endpoints must use explicit request and response schemas.

Use appropriate HTTP status codes.

Do not silently introduce breaking API changes.

API behavior must be consistent with the domain model.

For API changes, consult:

`docs/architecture/api.md`

---

# Frontend

The frontend is responsible for presentation and user interaction.

The backend remains the source of truth.

The frontend must:

* consume the backend API;
* handle loading and error states;
* provide appropriate user feedback;
* keep server state separate from local UI state;
* respect backend authorization;
* derive Kanban columns from project statuses.

Do not hardcode:

* status names;
* status IDs;
* workflow order;
* number of Kanban columns.

---

# Testing

Behavioral changes require appropriate tests.

Tests should verify behavior rather than implementation details.

Depending on the change, consider:

* successful operation;
* authentication;
* authorization;
* validation;
* not found;
* organization isolation;
* project isolation;
* cross-project workflow integrity;
* regression behavior.

For workflow changes, explicitly test that a task cannot reference a status belonging to another project.

For API changes, test both successful and invalid requests.

---

# Documentation

Documentation is part of the implementation.

When introducing a new domain concept:

1. Check `docs/product/glossary.md`.
2. Check relevant product requirements.
3. Check relevant architecture documentation.
4. Update the documentation if the concept is new or its meaning changes.

When making an architectural decision that is expected to remain relevant, add an ADR under:

`docs/architecture/decisions/`

Do not duplicate large sections of documentation inside `AGENTS.md`.

`AGENTS.md` contains operational rules.

`docs/` contains product and architectural knowledge.

---

# Tasks

Concrete implementation work should be represented by task documents under:

`docs/tasks/`

A task should define:

* goal;
* context;
* requirements;
* acceptance criteria;
* affected areas;
* API changes;
* database changes;
* authorization requirements;
* tests;
* dependencies;
* definition of done.

When implementing a task:

1. Read the task.
2. Inspect the existing implementation.
3. Identify affected modules and layers.
4. Check relevant documentation.
5. Implement the smallest complete solution.
6. Add or update tests.
7. Run relevant validation.
8. Review the final diff.

Do not implement unrelated improvements while working on a task.

---

# Scope control

Avoid:

* speculative abstractions;
* unnecessary refactoring;
* unrelated formatting changes;
* premature optimization;
* introducing infrastructure that is not required;
* implementing non-MVP functionality without an explicit requirement.

If a requested change requires a significant architectural decision, identify it before implementation and consult the relevant architecture documentation.

---

# Dependency changes

Do not add dependencies without a concrete reason.

Before adding a dependency:

1. Check whether the existing stack already provides the required functionality.
2. Consider maintenance and security implications.
3. Keep the dependency narrowly scoped.
4. Update the appropriate dependency files.
5. Run relevant validation.

---

# Secrets and sensitive data

Never commit:

* passwords;
* API keys;
* access tokens;
* private keys;
* production credentials;
* real user secrets.

Use environment variables or the project's configured secret-management mechanism.

Never expose secrets in logs, test fixtures, API responses, or error messages.

---

# Logging and errors

Logs should contain enough context to diagnose failures without exposing sensitive information.

Do not silently swallow exceptions.

Do not use broad exception handling unless there is a concrete recovery or translation requirement.

API errors should be predictable and consistent.

---

# Git and changes

Keep changes focused.

Do not rewrite unrelated code.

Do not modify generated files manually unless the task explicitly requires it.

Before finishing:

* inspect the diff;
* remove debugging code;
* remove temporary files;
* verify migrations;
* verify tests;
* verify formatting and linting where applicable.

---

# Completion criteria

A task is complete only when:

* the requested behavior is implemented;
* acceptance criteria are satisfied;
* domain invariants are preserved;
* authorization is enforced;
* database migrations exist when required;
* relevant tests are added or updated;
* relevant validation passes;
* API contracts remain consistent;
* no unrelated changes were introduced;
* the final diff has been reviewed.

---

# Working style

Prefer evidence over assumptions.

Inspect the existing code before changing it.

Reuse existing project patterns when they are appropriate.

Do not invent missing requirements.

If a requirement is ambiguous and the ambiguity affects architecture, data integrity, security, or API behavior, stop and ask for clarification.

For small, low-risk ambiguities, choose the simplest behavior consistent with the existing code and documentation.

Keep implementations understandable to another developer.

---

# Codex-specific guidance

Use the repository's `AGENTS.md` files as the primary source of operational instructions.

More specific `AGENTS.md` files apply to files inside their directory.

When working inside:

* `backend/` — follow `backend/AGENTS.md`;
* `frontend/` — follow `frontend/AGENTS.md`.

Do not require yourself to read every document in the repository before every change.

Read documentation according to the task.

Use task and project documentation as durable project context rather than copying that information into prompts.

When a change exposes a conflict between existing code and documented requirements, identify the conflict explicitly before choosing a solution.

---

# Final response

After completing a task, report:

1. What changed.
2. Important implementation decisions.
3. Tests and validation performed.
4. Migrations or API changes, if any.
5. Any remaining risks or follow-up work.

Keep the final report concise and factual.
