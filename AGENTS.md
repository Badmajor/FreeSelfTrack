# Task Tracker — Agent Instructions

## 1. Project

Task Tracker — self-hosted task tracking system inspired by products such as
Yandex Tracker.

The project is intended for teams that need:

- projects;
- tasks;
- configurable workflows;
- Kanban boards;
- comments;
- task history;
- watchers;
- tags;
- attachments;
- search;
- saved filters;
- notifications;
- dashboards.

The primary goal of the MVP is to provide a reliable and understandable
task tracker without unnecessary enterprise complexity.

---

# 2. Core principles

These rules have priority over local implementation preferences.

## 2.1 Backend is the source of truth

Business rules are enforced by the backend.

Frontend must not be considered a security boundary.

Frontend validation is allowed for UX,
but every important rule must also be validated on the backend.

---

## 2.2 Project owns its workflow

This is one of the most important domain rules.

The relationship is:

    Organization
        ↓
      Project
        ↓
    ProjectStatus
        ↓
       Task

A Project owns its statuses.

Example:

    Project A
        Backlog
        Development
        Review
        Done

    Project B
        Ideas
        Planning
        Approval
        Published

These are independent workflows.

Never assume that all projects use the same statuses.

---

## 2.3 Status is the Kanban column

For MVP there is no separate KanbanColumn domain entity.

A Kanban board is a visual representation of ProjectStatus.

Therefore:

    ProjectStatus = Kanban column

The backend provides:

- status ID;
- name;
- order;
- project;
- active/archive state;
- other status properties required by the UI.

The frontend renders columns from the API.

Never hardcode:

- status IDs;
- status names;
- number of columns;
- workflow order.

---

## 2.4 Task cannot use a status from another project

This invariant must always hold:

    task.project_id == task.status.project_id

A request such as:

    PATCH /tasks/123
    {
        "status_id": 999
    }

must fail if status `999` belongs to another project.

This must be enforced by backend business logic.

Do not rely on the frontend to prevent this.

---

## 2.5 MVP means simplicity

Do not introduce architecture merely because it might be useful in the future.

Prefer:

    simple implementation
        >
    unnecessary abstraction

Do not introduce:

- microservices;
- event sourcing;
- CQRS;
- workflow engines;
- service mesh;
- complex plugin systems;
- distributed transactions;
- unnecessary message brokers;

unless a concrete requirement requires them.

The MVP is a modular monolith.

---

# 3. Technology stack

## Backend

- Python 3.13+
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- Alembic
- PostgreSQL
- Redis
- pytest
- Ruff
- mypy

## Frontend

- TypeScript
- React
- Vite
- React Router
- TanStack Query
- ESLint

## Infrastructure

- Docker
- Docker Compose
- PostgreSQL
- Redis
- S3-compatible object storage

The exact dependency versions are defined by project configuration files.

Do not introduce alternative libraries without a concrete reason.

---

# 4. Repository structure

Expected structure:

    .
    ├── AGENTS.md
    ├── README.md
    ├── Makefile
    ├── docker-compose.yml
    ├── .env.example
    │
    ├── docs/
    │   ├── product/
    │   ├── architecture/
    │   └── development/
    │
    ├── backend/
    │   ├── AGENTS.md
    │   ├── app/
    │   ├── migrations/
    │   └── tests/
    │
    ├── frontend/
    │   ├── AGENTS.md
    │   ├── src/
    │   └── tests/
    │
    ├── infrastructure/
    │
    └── .github/
        ├── agents/
        ├── instructions/
        ├── workflows/
        └── ISSUE_TEMPLATE/

Directory-specific AGENTS.md files may add more restrictive rules.

If a local AGENTS.md conflicts with this file,
the more specific directory-level instruction applies to that directory.

---

# 5. Important documentation

Before implementing a non-trivial feature, inspect:

    docs/product/requirements.md
    docs/product/roadmap.md
    docs/product/glossary.md

For architectural decisions inspect:

    docs/architecture/overview.md
    docs/architecture/decisions/

For API-related work inspect:

    docs/architecture/api.md

Do not make architectural assumptions when the answer already exists
in project documentation.

---

# 6. Domain model

The initial domain consists of:

    Organization
    User
    Team
    Project
    ProjectMember
    ProjectStatus
    TaskType
    Task
    Priority
    Tag
    Comment
    Attachment
    Watcher
    TaskHistory
    SavedFilter
    Notification

Additional entities may be introduced when a concrete requirement requires them.

Do not create entities simply to make the architecture look more complete.

---

# 7. Organization boundaries

Organizations are isolated tenants.

A user must not be able to access another organization's data.

The normal access chain is:

    User
      ↓
    Organization membership
      ↓
    Project membership
      ↓
    Project resource

Every API endpoint that accesses organization-owned resources
must enforce the appropriate authorization boundary.

---

# 8. Authorization

Authentication and authorization are different concerns.

Authentication answers:

    "Who is the user?"

Authorization answers:

    "Can this user perform this operation?"

Never treat an authenticated user as automatically authorized
to access a resource.

Check authorization for:

- projects;
- project members;
- tasks;
- comments;
- attachments;
- statuses;
- task types;
- filters;
- project settings;
- administrative operations.

Pay particular attention to IDOR vulnerabilities.

For example:

    GET /api/projects/123

must not return Project 123 merely because the user is authenticated.

---

# 9. API architecture

Expected backend flow:

    HTTP request
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

Responsibilities:

### Router

Responsible for:

- HTTP;
- request parsing;
- dependencies;
- response status;
- response schema.

Router should not contain substantial business logic.

### Schema

Responsible for:

- request validation;
- response serialization;
- API contract.

### Service

Responsible for:

- business rules;
- workflows;
- authorization-related domain checks;
- transactions where appropriate.

### Repository

Responsible for:

- database queries;
- persistence;
- query composition.

Do not scatter SQLAlchemy queries across routers.

---

# 10. Database rules

PostgreSQL is the primary relational database.

Use SQLAlchemy 2.x.

Every schema change requires a new Alembic migration.

Never modify an already-applied migration.

Prefer database constraints for invariants that the database can enforce.

Examples:

- unique values;
- foreign keys;
- not-null fields;
- valid relationships.

Every foreign key must have an intentional deletion policy.

Choose explicitly between:

- CASCADE;
- SET NULL;
- RESTRICT;
- NO ACTION.

Do not rely on accidental database defaults.

---

# 11. Transactions

A business operation that modifies several related records
should have an explicit transaction boundary.

Examples:

Creating a project may involve:

    Project
    ProjectMember
    default ProjectStatus
    default TaskType

Changing a task status may involve:

    Task
    TaskHistory

These operations must not leave partially updated state.

---

# 12. Database performance

Avoid N+1 queries.

For list endpoints, think explicitly about:

- pagination;
- filtering;
- sorting;
- indexes;
- joins;
- eager loading.

Do not add indexes blindly.

Every non-trivial index should correspond to a real query pattern.

---

# 13. API compatibility

API contracts are public contracts.

Do not silently introduce breaking changes.

When changing an existing endpoint, consider:

- existing clients;
- generated frontend API clients;
- response schemas;
- request schemas;
- status codes;
- pagination;
- filters.

If a breaking change is unavoidable,
document it explicitly.

---

# 14. Frontend architecture

Frontend consumes backend APIs.

Do not duplicate backend domain state unnecessarily.

Server state should be handled through the project's configured
query/data-fetching mechanism.

Components should remain reasonably small.

Avoid components that simultaneously contain:

- API implementation;
- business rules;
- complex state management;
- layout;
- forms;
- rendering.

Separate responsibilities when complexity warrants it.

---

# 15. Kanban rules

Kanban is project-specific.

The board is derived from:

    ProjectStatus[]

The backend determines:

- available columns;
- column order;
- status IDs;
- status names;
- active/inactive state.

The frontend renders them dynamically.

Never write code like:

    if status === "done"

when the behavior actually depends on project configuration.

If special behavior depends on a status,
prefer explicit backend metadata or a documented domain property
instead of matching the display name.

---

# 16. Task movement

Moving a task between Kanban columns means changing its ProjectStatus.

The operation must:

1. authenticate the user;
2. verify project access;
3. verify target status belongs to the task's project;
4. update the task;
5. create history when required;
6. return the resulting task state.

A failed operation must not leave partial state.

---

# 17. Project status lifecycle

Statuses may be:

- created;
- renamed;
- reordered;
- archived;
- restored if supported.

Archiving a status requires an explicit policy
for tasks currently assigned to that status.

Do not silently delete statuses that are referenced by tasks.

The implementation must define what happens to existing tasks.

---

# 18. Task ordering

Kanban task order is independent from status.

A task has:

    project
    status
    order

Moving a task may therefore require:

- changing status;
- changing position.

Do not use database IDs as visual ordering.

Do not assume task creation order equals Kanban order.

---

# 19. User-specific board settings

Project workflow is shared.

Visual preferences may be user-specific.

For example:

    Project
        Status order ← project-level

    User + Project + Status
        Column width ← user-level

Do not mix project workflow configuration with user preferences.

---

# 20. Search and filters

Search and filtering are backend responsibilities.

For list endpoints:

- filter on server;
- sort on server;
- paginate on server.

Do not load an entire dataset into the browser
and filter it there unless the dataset is explicitly small and local.

Saved filters belong to the user/project context as defined by the domain model.

---

# 21. Background jobs

Background processing may be used for:

- email notifications;
- file processing;
- other operations that do not need to block the request.

Do not move normal synchronous business logic
into background jobs without a reason.

A request should not return success before required transactional state
has actually been persisted.

---

# 22. Notifications

Notifications may be:

- in-app;
- email.

Notification generation must not expose sensitive information.

Do not send passwords, tokens, secrets or private internal data
through notification messages.

---

# 23. Files

Attachments are stored in S3-compatible object storage.

Database stores metadata and references.

Do not store large binary files directly in PostgreSQL
unless explicitly required.

Validate:

- file size;
- MIME type where appropriate;
- filename;
- authorization.

A user must not be able to access another user's/project's attachment
by guessing its identifier.

---

# 24. Logging

Use the project's logging system.

Do not use:

    print()

for application logging.

Never log:

- passwords;
- access tokens;
- refresh tokens;
- cookies;
- authorization headers;
- secrets;
- sensitive personal information.

Logs should help diagnose failures without exposing credentials.

---

# 25. Error handling

Errors should be explicit.

Use appropriate HTTP status codes.

Do not catch broad exceptions unless handling them
at a deliberate application boundary.

Do not silently ignore exceptions.

Do not return internal stack traces to API clients.

---

# 26. Testing

Every behavior change requires appropriate tests.

At minimum, consider:

- happy path;
- validation;
- authentication;
- authorization;
- not found;
- isolation;
- regression.

For domain changes prefer integration tests when they provide
more confidence than heavily mocked unit tests.

Important workflow tests include:

- different projects can have different statuses;
- task status belongs to its project;
- task cannot move to another project's status;
- Kanban reflects project statuses;
- moving a task updates its status;
- history is created when required;
- project access is enforced.

---

# 27. Test isolation

Tests must be:

- deterministic;
- isolated;
- repeatable;
- independent.

Tests must not depend on execution order.

Do not use production databases.

Do not use real external services unless the test is explicitly
an integration test designed for that service.

---

# 28. Migrations

When a model/schema changes:

1. update the model;
2. create a migration;
3. inspect generated migration;
4. correct it manually if necessary;
5. test upgrade;
6. test downgrade when supported;
7. test against representative existing data when the migration
   can affect existing rows.

Never blindly trust autogenerated migrations.

---

# 29. Git workflow

Primary branches:

    main
    develop

Feature branches:

    feature/<description>

Bug fixes:

    fix/<description>

Do not work directly on `main`.

Keep commits focused.

Avoid mixing:

- feature implementation;
- unrelated refactoring;
- formatting entire directories;
- dependency upgrades

in one change unless necessary.

---

# 30. Scope control

An agent must not modify unrelated files.

If a task is:

    "Add project statuses"

do not additionally:

- redesign authentication;
- rewrite unrelated repositories;
- change frontend styling globally;
- upgrade dependencies;
- rename unrelated classes.

Small changes are easier to review and safer to merge.

---

# 31. Existing code has priority over assumptions

Before creating a new implementation:

1. search the repository;
2. find similar functionality;
3. understand existing conventions;
4. reuse existing infrastructure.

Do not introduce duplicate:

- helpers;
- repositories;
- services;
- API clients;
- validation;
- components.

---

# 32. Dependencies

Do not add a dependency without a concrete reason.

Before adding a library:

1. check whether the functionality already exists;
2. check existing project dependencies;
3. consider maintenance cost;
4. consider security;
5. consider bundle/image size;
6. document the reason if significant.

---

# 33. Security

Treat all client input as untrusted.

Pay particular attention to:

- authorization;
- object-level access;
- file uploads;
- SQL queries;
- XSS;
- CSRF where applicable;
- secrets;
- SSRF;
- path traversal;
- unsafe deserialization.

Never commit secrets.

Never hardcode credentials.

Never disable security checks merely to make tests pass.

---

# 34. Documentation

Update documentation when a change affects:

- architecture;
- API;
- database model;
- developer workflow;
- environment variables;
- deployment;
- product behavior.

Architectural decisions that have long-term consequences
should be recorded as ADRs.

---

# 35. Agent behavior

Agents must:

1. Understand the task.
2. Inspect the relevant code.
3. Read applicable instructions.
4. Make the smallest correct change.
5. Add/update tests.
6. Run relevant validation.
7. Review their own changes.
8. Report what changed.

Do not pretend that a command was executed if it was not.

Do not claim tests pass without running them.

If a command cannot be executed,
say so explicitly.

---

# 36. When requirements are ambiguous

Do not invent important product behavior.

If ambiguity affects:

- data model;
- authorization;
- API contract;
- workflow;
- destructive behavior;
- compatibility;

stop and ask for clarification.

For minor implementation details,
choose the simplest solution consistent with existing architecture.

---

# 37. Definition of Done

A change is complete only when applicable items are satisfied:

- [ ] Requirements implemented.
- [ ] Existing architecture respected.
- [ ] Authorization implemented.
- [ ] Validation implemented.
- [ ] Tests added or updated.
- [ ] Existing relevant tests pass.
- [ ] Lint passes.
- [ ] Type checking passes.
- [ ] Migration added if required.
- [ ] Migration reviewed.
- [ ] API documentation updated if required.
- [ ] No secrets introduced.
- [ ] No unrelated changes.
- [ ] Documentation updated if required.

Recommended checks:

    make format
    make lint
    make typecheck
    make test

For frontend changes also run:

    make test-frontend
    make build-frontend

For infrastructure changes also run:

    docker compose config

---

# 38. Final response format

After completing a task, provide a concise summary:

## Changed

List important changes.

## Files

List modified/created files.

## Database

Mention migrations, if any.

## Tests

Mention tests added/changed.

## Validation

List commands actually executed and their results.

## Notes

Mention unresolved issues, assumptions, or follow-up work.

Do not claim successful validation if it was not actually executed.


## Domain terminology

The canonical domain terminology is defined in:

`docs/product/glossary.md`

Agents MUST read the glossary when working on domain models, API contracts,
business logic, tasks, frontend domain components, or documentation.

The glossary is the source of truth for domain terminology.
Do not introduce synonyms for core domain entities without updating the glossary.
