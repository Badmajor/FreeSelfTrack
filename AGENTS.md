## Project

This repository contains a free self-hosted task tracker.

The application is a modular monolith.

## Product documentation

Use these documents when relevant:

- `docs/product/requirements.md` — product requirements and MVP scope.
- `docs/product/glossary.md` — canonical domain terminology.
- `docs/product/roadmap.md` — planned product development.

## Architecture documentation

Use these documents when relevant:

- `docs/architecture/overview.md` — system architecture.
- `docs/architecture/api.md` — API conventions.
- `docs/architecture/decisions/` — accepted architectural decisions.

Do not read all documentation by default. Read the documents relevant to the current task.

## Core domain invariants

The task workflow is project-owned:

Project -> ProjectStatus -> Task

`ProjectStatus` is both:

- a task status;
- a Kanban column.

There is no separate global Status entity or KanbanColumn entity in the MVP.

A task status must belong to the same project as the task.

Kanban columns are derived from ProjectStatus.

Column width is a user-specific board preference and does not modify the project workflow.

## Architecture

The backend is a modular monolith.

Keep responsibilities separated:

Router
-> Schema
-> Authorization
-> Service
-> Repository
-> Database

Business logic must not be placed in routers.

Database access must not be scattered throughout the application.

## Security

Always enforce:

- organization boundaries;
- project access;
- object-level authorization;
- protection against IDOR.

Never assume that knowing an object ID grants access to the object.

## Database

PostgreSQL is the primary database.

SQLAlchemy 2.x is used for ORM/data access.

Alembic is used for migrations.

Every schema change requires an Alembic migration.

Do not modify existing migrations that may already have been applied.

## API

FastAPI is used for the REST API.

Use explicit Pydantic request and response schemas.

Do not expose SQLAlchemy models directly through API endpoints.

Do not introduce breaking API changes without an explicit requirement.

## Testing

Behavioral changes require appropriate tests.

At minimum consider:

- success;
- authentication;
- authorization;
- validation;
- not found;
- organization/project isolation;
- regression cases.

## Documentation

When introducing a new domain concept or changing an existing concept:

1. Check `docs/product/glossary.md`.
2. Check the relevant architecture documentation.
3. Update documentation if the change modifies an established concept.

## Development workflow

Before implementing a non-trivial task:

1. Understand the requirements.
2. Inspect the relevant existing code.
3. Identify affected layers.
4. Implement the smallest complete solution.
5. Add or update tests.
6. Run relevant validation.
7. Review the final diff.

Do not make unrelated refactors.

## Scope

Implement only what is required for the current task.

Do not introduce speculative features, abstractions, integrations, or architecture.

## Task completion

A task is complete only when:

- acceptance criteria are satisfied;
- relevant tests pass;
- migrations are created when required;
- API contracts are consistent;
- authorization is covered;
- no known regression is introduced;
- the final diff has been reviewed.
