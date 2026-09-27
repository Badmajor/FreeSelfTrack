# Create Feature

You are implementing a new product feature in the Task Tracker repository.

The feature may span:

- backend;
- database;
- API;
- frontend;
- tests;
- infrastructure.

Do not immediately start coding.

---

# 1. Understand the feature

Read:

- `AGENTS.md`;
- relevant nested `AGENTS.md`;
- `docs/product/requirements.md`;
- `docs/product/roadmap.md`;
- `docs/product/glossary.md`;
- relevant architecture documentation;
- applicable path-specific instructions.

Search the existing codebase for related functionality.

---

# 2. Define acceptance criteria

Convert the feature description into explicit acceptance criteria.

Each criterion must be testable.

Example:

    Given a project has statuses A, B and C,
    when the user reorders statuses,
    then the new order is persisted
    and the Kanban board uses that order.

Avoid vague criteria such as:

    "Statuses should work correctly."

---

# 3. Domain impact

Determine whether the feature changes:

- Organization;
- Project;
- ProjectStatus;
- Task;
- permissions;
- notifications;
- history;
- user preferences.

Do not create a new entity unless the domain actually requires one.

---

# 4. Architecture

Determine:

### Backend

Services, repositories and schemas.

### Database

Models, constraints, indexes and migration.

### API

Endpoints and contracts.

### Frontend

Pages, components, state and queries.

### Tests

Unit, integration and E2E coverage.

---

# 5. Preserve existing invariants

Pay special attention to:

    Organization isolation

    Project authorization

    Project-owned workflow

    Task/status consistency

    Backend as source of truth

    No hardcoded Kanban workflow

---

# 6. Implementation plan

Produce a phased plan.

Example:

    Phase 1 — Database
    Phase 2 — Backend domain
    Phase 3 — API
    Phase 4 — Frontend
    Phase 5 — Tests
    Phase 6 — Validation

Keep each phase independently understandable.

---

# 7. Implement

Implement the feature incrementally.

After each meaningful layer,
verify that the implementation remains consistent.

Do not create speculative abstractions for future requirements.

---

# 8. Database

If the feature changes the schema:

- update models;
- create migration;
- inspect generated SQL;
- consider existing data;
- test migration;
- verify rollback behavior where applicable.

Never modify an already-applied migration.

---

# 9. API

For API changes:

- define request schemas;
- define response schemas;
- validate authorization;
- document behavior;
- preserve backwards compatibility where possible.

---

# 10. Frontend

For frontend implementation:

- consume backend API;
- use existing query layer;
- handle loading/error/empty states;
- do not duplicate business rules.

For Kanban-related features,
derive UI from dynamic ProjectStatus data.

---

# 11. Tests

Write tests from acceptance criteria.

Required categories where applicable:

- success;
- validation;
- authentication;
- authorization;
- isolation;
- edge cases;
- regression.

Do not optimize for coverage percentage.

Optimize for confidence in behavior.

---

# 12. Validation

Run relevant project checks.

Do not claim checks were executed unless they actually were.

---

# 13. Final review

Before completion:

- inspect git diff;
- remove unrelated changes;
- verify migrations;
- verify authorization;
- verify tests;
- verify API;
- verify frontend;
- verify documentation.

---

# Final response

Return:

## Feature

What was implemented.

## Acceptance criteria

List each criterion and whether it is satisfied.

## Changes

Backend / database / API / frontend.

## Tests

Tests added or changed.

## Validation

Commands actually executed.

## Follow-up

Only genuinely necessary future work.
