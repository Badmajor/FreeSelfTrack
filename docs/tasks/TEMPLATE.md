# TASK-XXX: <Task title>

## Goal

What should be achieved by completing this task?

Keep this section short and outcome-oriented.

---

## Context

Why is this task needed?

Reference relevant product or architecture documentation when applicable.

---

## Requirements

### Functional requirements

* Requirement 1
* Requirement 2
* Requirement 3

### Technical requirements

* Technical requirement 1
* Technical requirement 2

---

## Acceptance Criteria

The task is considered functionally complete when:

* [ ] Criterion 1
* [ ] Criterion 2
* [ ] Criterion 3

Acceptance criteria must be observable and testable.

---

## Domain

Describe affected domain entities and invariants.

Relevant entities:

* `Entity`

Relevant invariants:

* Invariant 1
* Invariant 2

If this task changes an existing domain concept, check:

`docs/product/glossary.md`

---

## Architecture

Describe which parts of the system are affected.

Potential areas:

* Backend
* Frontend
* Database
* API
* Infrastructure

Reference relevant architecture documentation and ADRs.

---

## API

Complete this section only when the task affects the API.

### Endpoints

```text
METHOD /api/...
```

### Request

Describe request parameters or body.

### Response

Describe response.

### Errors

Describe relevant error cases and HTTP status codes.

---

## Database

Complete this section only when the task affects the database.

### Changes

* Table/entity changes
* Columns
* Constraints
* Indexes
* Relationships

### Migration

A new Alembic migration is required:

* [ ] Yes
* [ ] No

Migration considerations:

* ...

---

## Authorization

Describe who can perform the operation.

Consider:

* authentication;
* organization boundary;
* project membership;
* object-level authorization;
* IDOR;
* cross-project access.

---

## Frontend

Complete this section when the task affects the frontend.

Describe:

* affected screens;
* components;
* API usage;
* user interactions;
* loading states;
* error states;
* accessibility requirements.

---

## Tests

Describe required tests.

### Backend

* [ ] Unit tests
* [ ] Integration tests
* [ ] API tests
* [ ] Authorization tests

### Frontend

* [ ] Component tests
* [ ] Interaction tests
* [ ] API/state tests

### Regression

* [ ] Regression test required

Specific scenarios:

* ...

---

## Dependencies

List tasks or changes that must be completed first.

* `TASK-XXX`
* None

---

## Validation

Commands that should be run before completion.

```text
# Backend
...

# Frontend
...

# Other
...
```

---

## Definition of Done

* [ ] Requirements implemented.
* [ ] Acceptance criteria satisfied.
* [ ] Domain invariants preserved.
* [ ] Authorization implemented and tested.
* [ ] Database migration created when required.
* [ ] API contract updated when required.
* [ ] Relevant tests added or updated.
* [ ] Relevant validation passed.
* [ ] Documentation updated when required.
* [ ] Final diff reviewed.
* [ ] No unrelated changes introduced.

---

## Implementation Notes

Use this section to record important implementation decisions made during the task.

Keep decisions concise.

If a decision is architectural and should remain relevant beyond this task, create or update an ADR under:

`docs/architecture/decisions/`

---

## Status

* Status: TODO
* Started:
* Completed:

### Progress

* [ ] Analysis
* [ ] Implementation
* [ ] Tests
* [ ] Validation
* [ ] Review

### Known issues

* None
