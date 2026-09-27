# Backend instructions

## Stack

- Python
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- Alembic
- PostgreSQL
- Redis
- pytest
- Ruff
- mypy

## Architecture

app/
├── api/
├── models/
├── schemas/
├── repositories/
├── services/
├── dependencies/
└── core/

### api

HTTP layer only.

Routers must not contain business logic.

### schemas

Pydantic request/response models.

### models

SQLAlchemy models.

### repositories

Database queries.

### services

Business logic.

### dependencies

FastAPI dependencies.

## Database

All schema changes require Alembic migration.

Never use automatic database schema creation in production.

Never modify an already applied migration.

## API

Use REST semantics.

Use explicit response schemas.

Do not return SQLAlchemy models directly from endpoints.

## Tests

Every service should have unit tests.

Every API endpoint should have integration tests.
