
---
applyTo: "**/tests/**/*.{py,ts,tsx},**/*test*.{py,ts,tsx},**/*spec*.{py,ts,tsx}"
---

# Testing Instructions

## General

Tests are part of the feature implementation.

A feature is not complete if required tests are missing.

Tests must be:

- deterministic;
- isolated;
- readable;
- repeatable.

## Test pyramid

Prefer:

1. unit tests for business logic;
2. integration tests for database/API behavior;
3. E2E tests for critical user flows.

Do not replace all unit/integration tests with E2E tests.

## Unit tests

Unit tests should test business behavior independently from external infrastructure when practical.

Mock external systems only when necessary.

Do not mock the entire application just to make a test pass.

## Integration tests

Use a real test database for database integration tests where practical.

Test real:

- SQLAlchemy queries;
- constraints;
- transactions;
- API/database interaction.

## API tests

Every important API endpoint should test at least:

- successful request;
- authentication failure;
- authorization failure;
- validation failure;
- not-found behavior where applicable.

## Authorization tests

Authorization must be tested explicitly.

For example:

```text
User A → Project A → allowed
User A → Project B → forbidden
````

Do not assume authorization works because the frontend hides a button.

## Domain tests

Important domain rules require tests.

For this project:

```text
Project A can have:
Backlog → Development → Review → Done

Project B can have:
Ideas → Planning → Approval → Published
```

Changing Project A statuses must not affect Project B.

## Kanban tests

Test that:

* columns are derived from project statuses;
* task appears in the correct status column;
* moving a task changes its status;
* invalid project/status combinations are rejected;
* status changes create history entries.

## Fixtures

Prefer reusable fixtures/factories.

Avoid large duplicated setup blocks.

Use realistic but minimal test data.

## Test naming

Test names should describe behavior.

Prefer:

```text
test_user_cannot_update_task_from_another_project
```

over:

```text
test_update_task_2
```

## Regression tests

Every discovered bug should receive a regression test when practical.

The test should fail before the fix and pass after the fix.

## Avoid brittle tests

Do not depend on:

* exact database IDs unless necessary;
* timestamps without controlling time;
* execution order;
* implementation-specific HTML structure;
* internal function calls when testing user behavior.

## Test completion

Before completing a task:

```bash
make test
```

For backend changes also run:

```bash
make test-backend
```

For frontend changes:

```bash
make test-frontend
```

For critical cross-system changes:

```bash
make test-integration
```
