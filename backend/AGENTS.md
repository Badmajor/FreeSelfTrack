# Backend Agent Instructions

This file contains backend-specific rules.

The root `AGENTS.md` remains authoritative for project-wide
architecture, domain rules, security and Definition of Done.

---

# 1. Backend responsibility

The backend is responsible for:

- REST API;
- authentication;
- authorization;
- business rules;
- database persistence;
- project workflows;
- task management;
- comments;
- history;
- watchers;
- notifications;
- search and filtering;
- file metadata;
- background processing.

The backend is the source of truth for business behavior.

---

# 2. Technology

Use:

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

Do not introduce alternative frameworks or ORMs
without an explicit architectural reason.

---

# 3. Expected structure

The backend should generally follow:

    backend/
    ├── app/
    │   ├── main.py
    │   ├── core/
    │   ├── db/
    │   ├── api/
    │   ├── models/
    │   ├── schemas/
    │   ├── repositories/
    │   ├── services/
    │   └── dependencies/
    │
    ├── migrations/
    └── tests/

The exact structure may evolve.

Do not reorganize directories unless the task requires it.

---

# 4. API layer

API routers should be thin.

A typical endpoint should look conceptually like:

    request
      ↓
    dependency injection
      ↓
    authentication
      ↓
    authorization
      ↓
    schema validation
      ↓
    service
      ↓
    response schema

Do not put substantial business logic inside routers.

Avoid:

    @router.post(...)
    async def create_task(...):
        # 100 lines of business logic

Prefer:

    @router.post(...)
    async def create_task(...):
        return await task_service.create(...)

---

# 5. Services

Services contain business logic.

Examples:

    ProjectService
    ProjectStatusService
    TaskService
    CommentService
    NotificationService

A service should answer questions such as:

- Can this user modify this project?
- Can this task use this status?
- What happens when a status is archived?
- Should task history be created?
- Should a notification be generated?

Services should not depend on HTTP-specific concepts
unless there is a strong reason.

Do not raise HTTPException deep inside domain/service code
when a domain/application exception is more appropriate.

---

# 6. Repositories

Repositories encapsulate database access.

Repository responsibilities:

- select;
- insert;
- update;
- delete;
- filtering;
- sorting;
- pagination;
- eager loading.

Repositories should not contain application workflow.

Bad:

    repository.move_task_to_status(...)

if this operation also requires:

- permission checks;
- history;
- notifications;
- validation.

Prefer:

    TaskService.move_task(...)

which coordinates repositories.

---

# 7. SQLAlchemy

Use SQLAlchemy 2.x style.

Prefer:

    select(Task)
    .where(Task.project_id == project_id)

Avoid legacy query APIs.

Use explicit relationships.

Avoid implicit lazy loading in async request paths
when it can result in unexpected database queries.

Use appropriate loading strategies such as:

- selectinload;
- joinedload;

when justified.

---

# 8. Async code

FastAPI endpoints are asynchronous unless there is a concrete reason otherwise.

Use:

    async def

for I/O-bound application code.

Database access uses:

    AsyncSession

Do not use blocking operations inside async request handlers.

Avoid:

    requests
    synchronous database drivers
    blocking subprocesses
    blocking filesystem operations

unless deliberately isolated from the async event loop.

---

# 9. Pydantic

Use Pydantic schemas for API boundaries.

Separate schemas when necessary:

    TaskCreate
    TaskUpdate
    TaskRead
    TaskListItem

Do not expose SQLAlchemy models directly through API endpoints.

For ORM serialization use:

    ConfigDict(from_attributes=True)

where appropriate.

Use:

    extra="forbid"

for request schemas where silently accepting unknown fields
could hide client errors.

---

# 10. Authentication

Authentication establishes the current user.

Do not confuse authentication with authorization.

A dependency such as:

    get_current_user()

does NOT mean the user is allowed to access every resource.

After authentication, perform resource-level authorization.

---

# 11. Authorization

Authorization must be explicit.

Typical checks:

    User
      ↓
    Organization membership
      ↓
    Project membership
      ↓
    Resource ownership/access

Never trust:

- user_id from request body;
- organization_id from client;
- project_id from URL;
- task_id alone.

Always verify the relationship between the current user
and the requested resource.

---

# 12. IDOR protection

Every endpoint returning or modifying a resource must verify
that the current user can access that resource.

For example, this is insufficient:

    task = await repository.get(task_id)

Instead, the effective query or subsequent authorization
must establish that the task belongs to a project
accessible to the current user.

Do not rely on obscure IDs to provide security.

---

# 13. Project workflow

The backend must preserve:

    Project
        ↓
    ProjectStatus
        ↓
    Task

ProjectStatus belongs to exactly one Project.

Before assigning a status to a Task:

    target_status.project_id == task.project_id

must be true.

Otherwise reject the operation.

This check must happen server-side.

---

# 14. Project statuses

A Project can define its own statuses.

Statuses have an explicit order.

Example:

    Project A

    1. Backlog
    2. Development
    3. Review
    4. Done

Another project may have:

    Project B

    1. Ideas
    2. Planning
    3. Approval
    4. Published

Do not create global status constants such as:

    TODO_STATUS_ID = 1
    DONE_STATUS_ID = 5

Do not rely on status names for business logic.

---

# 15. Status lifecycle

When implementing status changes consider:

- tasks currently using the status;
- ordering;
- archived statuses;
- active statuses;
- project permissions.

Never silently delete a status that is referenced by tasks.

If deletion is supported,
the behavior for existing tasks must be explicitly defined.

Prefer archive/deactivate semantics when appropriate.

---

# 16. Task operations

Task operations must preserve domain invariants.

Creating a Task:

1. authenticate;
2. authorize project access;
3. validate task type;
4. validate status;
5. validate assignee if applicable;
6. persist task;
7. create related records if required.

Updating a Task:

1. authorize access;
2. validate changed fields;
3. validate status/project relationship;
4. apply changes;
5. create history where required;
6. commit atomically.

---

# 17. Task movement

Moving a task between Kanban columns means changing
its ProjectStatus.

The operation must validate:

    task.project_id == target_status.project_id

If task ordering is supported,
the operation may also update the task's position.

Do not implement movement as an arbitrary database update
without business validation.

---

# 18. History

Important task changes should be represented in TaskHistory.

Examples:

- status changed;
- assignee changed;
- priority changed;
- title changed when required;
- deadline changed when required.

History should be created within the same transaction
as the operation it describes.

Do not create history asynchronously if doing so could result
in successful task changes without corresponding history.

---

# 19. Transactions

Use a transaction when several changes must succeed or fail together.

Example:

    update task
    +
    create task history

must normally be atomic.

Do not commit after every repository operation
inside a multi-step business operation.

Prefer service-level transaction boundaries.

---

# 20. API design

Use REST conventions.

Examples:

    GET    /api/projects
    POST   /api/projects

    GET    /api/projects/{project_id}
    PATCH  /api/projects/{project_id}

    GET    /api/projects/{project_id}/statuses
    POST   /api/projects/{project_id}/statuses

    GET    /api/tasks/{task_id}
    PATCH  /api/tasks/{task_id}

Use nouns rather than RPC-style action names
unless an action is genuinely not representable as a normal resource update.

---

# 21. Status codes

Use explicit status codes.

Typical examples:

    200 OK
    201 Created
    204 No Content
    400 Bad Request
    401 Unauthorized
    403 Forbidden
    404 Not Found
    409 Conflict
    422 Unprocessable Entity

Choose the status according to the actual semantics.

Do not return 200 for every operation.

---

# 22. Pagination

Collection endpoints should support pagination
when the dataset can grow significantly.

Avoid:

    SELECT * FROM tasks

followed by Python-side slicing.

Pagination must happen at the database level.

---

# 23. Filtering

Filtering should be performed by PostgreSQL.

Example:

    GET /api/tasks?status_id=...&assignee_id=...

Do not load thousands of tasks
and filter them in Python.

---

# 24. Search

Search implementation should be designed around
actual query requirements.

For MVP, prefer PostgreSQL capabilities
before introducing a dedicated search engine.

Do not add Elasticsearch/OpenSearch unless requirements
actually justify it.

---

# 25. Database constraints

Business invariants that can safely be enforced by PostgreSQL
should also be represented at database level.

Examples:

- unique project key within organization;
- unique status order where appropriate;
- unique membership;
- foreign key relationships.

Application validation alone is not enough
for invariants vulnerable to race conditions.

---

# 26. Alembic

Every schema change requires a migration.

Workflow:

    change model
        ↓
    generate migration
        ↓
    inspect migration
        ↓
    correct migration if necessary
        ↓
    test upgrade
        ↓
    test downgrade when applicable

Never edit an already-applied migration.

Never delete old migrations to "clean up" history.

---

# 27. Migration safety

Be especially careful with:

- large table changes;
- non-null columns;
- destructive changes;
- foreign keys;
- indexes;
- enum changes;
- data migrations.

For existing data:

    schema migration
        +
    data migration

must be considered separately.

Do not assume the database is empty.

---

# 28. Redis

Redis is infrastructure, not the primary source of persistent domain state.

Use Redis for appropriate cases such as:

- caching;
- rate limiting;
- temporary state;
- background job coordination.

Do not move core task/project state into Redis
just to avoid database queries.

PostgreSQL remains the source of truth for domain data.

---

# 29. External services

External service calls should be isolated from domain logic.

Use dedicated clients/adapters.

Do not scatter HTTP calls throughout services.

Handle:

- timeouts;
- connection failures;
- invalid responses;
- retries where appropriate.

Never retry non-idempotent operations blindly.

---

# 30. Logging

Use structured application logging where available.

Log enough context to diagnose problems:

- operation;
- resource type;
- resource ID where safe;
- request correlation ID where available.

Never log:

- passwords;
- tokens;
- cookies;
- authorization headers;
- secrets.

---

# 31. Error handling

Use application/domain exceptions where appropriate.

Map them to HTTP responses at the API boundary.

Do not use broad exception handling to hide bugs.

Bad:

    try:
        ...
    except Exception:
        return None

This turns real failures into invisible corruption.

---

# 32. Testing

Backend tests are located under:

    backend/tests/

Use the project's existing test organization.

Prefer:

- unit tests for isolated logic;
- integration tests for database behavior;
- API tests for endpoint behavior.

Authorization and data isolation should be tested through
realistic API/integration scenarios.

---

# 33. Required workflow tests

When workflow functionality changes,
test at minimum:

1. Project A has its own statuses.
2. Project B has different statuses.
3. Task A uses Project A status.
4. Task A cannot use Project B status.
5. Kanban returns Project A statuses.
6. Task appears in its status column.
7. Moving task changes its status.
8. History is created.
9. Unauthorized users cannot modify the task.
10. Archived/inactive statuses behave according to the defined policy.

---

# 34. Code style

Use Ruff for formatting and linting.

Prefer explicit readable code over clever abstractions.

Type all public functions.

Avoid:

    Any

unless technically justified.

Avoid unnecessary metaprogramming.

Prefer composition over inheritance
unless inheritance represents a real domain or framework relationship.

---

# 35. Dependency injection

Use FastAPI dependency injection for:

- database sessions;
- current user;
- authorization context;
- infrastructure clients.

Do not instantiate infrastructure dependencies
inside every endpoint manually.

---

# 36. Backend Definition of Done

Before reporting completion:

    make format
    make lint
    make typecheck
    make test

If the change affects the database:

    make migration
    make migrate

The agent must report which commands were actually executed.

Never claim a check passed if it was not executed.
