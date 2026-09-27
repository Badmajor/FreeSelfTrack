# Implement Task

You are implementing a task in the Task Tracker repository.

## Task

Implement the task described by the user.

Before making changes, inspect the repository and determine:

1. Which part of the system is affected.
2. Which existing implementation is related.
3. Which architecture rules apply.
4. Whether database changes are required.
5. Whether API changes are required.
6. Whether frontend changes are required.
7. Which tests are required.

Do not start coding immediately.

First understand the existing implementation.

---

# Required workflow

Follow these steps in order.

## 1. Understand

Read:

- root `AGENTS.md`;
- relevant nested `AGENTS.md`;
- relevant `.github/instructions/*.instructions.md`;
- product requirements;
- relevant architecture documentation.

Search the repository for related functionality.

Do not duplicate existing functionality.

---

## 2. Plan

Before implementation, create a short implementation plan.

The plan must include:

### Scope

What will change.

### Backend

Backend changes, if any.

### Database

Models and migrations, if any.

### API

Endpoints and schemas, if any.

### Frontend

UI changes, if any.

### Tests

Tests that must be added or updated.

### Risks

Potential edge cases or compatibility issues.

Do not implement unrelated improvements.

---

## 3. Implement

Implement the smallest complete solution.

Follow existing project conventions.

Do not introduce new architectural patterns
unless the existing architecture cannot support the requirement.

Do not add dependencies unless necessary.

---

# Database requirements

If database schema changes are required:

1. Modify SQLAlchemy models.
2. Create an Alembic migration.
3. Inspect the migration.
4. Check existing data implications.
5. Test the migration.

Never modify an existing applied migration.

---

# API requirements

If API changes are required:

- define request schemas;
- define response schemas;
- implement authorization;
- use appropriate HTTP status codes;
- update OpenAPI-facing documentation where required;
- preserve compatibility where possible.

Do not expose SQLAlchemy models directly.

---

# Backend requirements

Business logic belongs in services.

Database access belongs in repositories.

Keep routers thin.

Validate resource ownership and authorization.

For project-owned resources verify:

    user
      ↓
    organization
      ↓
    project
      ↓
    resource

For task workflow verify:

    task.project_id == target_status.project_id

---

# Frontend requirements

If frontend changes are required:

- use existing API client;
- use existing query/data-fetching mechanisms;
- do not duplicate backend business logic;
- handle loading/error/empty states;
- add tests for observable behavior.

For Kanban:

    ProjectStatus[]
        ↓
    Kanban columns

Never hardcode project statuses.

---

# Testing

Add tests for the changed behavior.

At minimum consider:

- happy path;
- invalid input;
- authentication;
- authorization;
- not found;
- data isolation;
- regression cases.

If the task changes workflow behavior,
test project/status isolation explicitly.

---

# Validation

Run applicable checks.

Backend:

    make format
    make lint
    make typecheck
    make test

Frontend:

    make lint
    make typecheck
    make test-frontend
    make build-frontend

Infrastructure:

    docker compose config

Only report checks that were actually executed.

---

# Final review

Before finishing:

1. Review the diff.
2. Remove unrelated changes.
3. Check for debug code.
4. Check for secrets.
5. Check authorization.
6. Check migrations.
7. Check tests.
8. Check API compatibility.

---

# Final response

Return:

## Implemented

Short description.

## Changed files

List important files.

## Database

Describe migrations, if any.

## API

Describe API changes, if any.

## Tests

Describe tests added or changed.

## Validation

List commands actually executed.

## Notes

Mention assumptions, limitations or follow-up work.
