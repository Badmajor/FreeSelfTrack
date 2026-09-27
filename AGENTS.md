# Task Tracker

## Project

Task Tracker is a self-hosted issue and project management system.

The product provides:

- organizations;
- users;
- projects;
- configurable project statuses;
- tasks;
- Kanban boards;
- comments;
- attachments;
- watchers;
- filters;
- notifications.

## Architecture

The MVP is a monorepo.

Backend:
- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis

Frontend:
- TypeScript
- React

Infrastructure:
- Docker Compose
- PostgreSQL
- Redis
- S3-compatible object storage

## Core domain rule

Project owns its workflow.

ProjectStatus belongs to Project.

Task belongs to Project and references ProjectStatus.

Kanban columns are a visual representation of ProjectStatus.

Do not introduce a global status model unless explicitly required.

## Development rules

- Keep business logic out of API routers.
- Validate input using Pydantic schemas.
- Keep database access in repositories.
- Keep business operations in services.
- Every new feature must have tests.
- Every database schema change requires an Alembic migration.
- Never modify an existing migration that may already have been applied.
- Never expose secrets in source code.
- Do not silently change existing API contracts.

## Before finishing a task

Run:

1. formatter
2. linter
3. type checker
4. unit tests
5. integration tests when applicable

Do not mark a task complete if validation fails.

## Git

Keep commits focused.

Do not mix:
- refactoring;
- formatting;
- unrelated fixes

with the requested feature.
