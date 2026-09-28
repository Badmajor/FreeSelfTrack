# API Architecture

## 1. API Style

The backend exposes a REST API through FastAPI.

Base path:

```text
/api/
```

Resources use plural nouns where practical.

Examples:

```text
/api/organizations
/api/projects
/api/tasks
/api/comments
```

Avoid action-oriented URLs when a resource operation can be represented using normal HTTP semantics.

---

# 2. API Source of Truth

The FastAPI OpenAPI specification is the canonical API contract.

Pydantic schemas define request and response structures.

SQLAlchemy models must not be exposed directly.

---

# 3. Authentication

Protected endpoints require an authenticated user.

The exact authentication transport is defined by the authentication implementation.

The API must distinguish:

```text
401 Unauthorized
```

from:

```text
403 Forbidden
```

`401` means the request does not have valid authentication.

`403` means the authenticated user does not have permission to perform the requested operation.

---

## Authentication Endpoints

Public authentication endpoints:

```http
POST /api/auth/register
POST /api/auth/login
```

Registration accepts an email and password and returns the public user representation.
It never returns the password or password hash.

Login returns a bearer access token and public user representation:

```json
{
  "access_token": "token-value",
  "token_type": "bearer",
  "user": {
    "id": "user-uuid",
    "email": "user@example.com",
    "is_active": true
  }
}
```

Protected endpoints require:

```http
Authorization: Bearer <access-token>
```

Invalid credentials and invalid or missing tokens return `401 Unauthorized`. Duplicate registration email returns `409 Conflict`. Login errors use one generic message and must not disclose whether an email is registered.

---

# 4. Authorization

Authorization must be enforced server-side.

Every protected resource must be checked against the current user's organization/project access.

Do not rely on the frontend to hide unauthorized resources.

---

# 5. Resource Hierarchy

The primary domain hierarchy is:

```text
Organization
    └── Project
          ├── ProjectStatus
          └── Task
```

Additional task resources:

```text
Task
├── Comments
├── Attachments
├── Watchers
├── Tags
└── History
```

---

# 6. Organization Endpoints

Initial operations:

```http
POST /api/organizations
GET  /api/organizations
GET  /api/organizations/{organization_id}
```

The exact list/retrieve operations may be added when required by the UI.

---

# 7. Project Endpoints

Initial operations:

```http
POST /api/projects
GET  /api/projects/{project_id}
PATCH /api/projects/{project_id}
```

Projects must always be resolved within the authorization context of the current user.

---

# 8. Project Status Endpoints

Project statuses belong to a project.

Initial API:

```http
POST  /api/projects/{project_id}/statuses
GET   /api/projects/{project_id}/statuses
PATCH /api/projects/{project_id}/statuses/{status_id}
POST  /api/projects/{project_id}/statuses/reorder
```

The list endpoint must return statuses in workflow order.

Example:

```json
[
  {
    "id": "status-1",
    "name": "Backlog",
    "position": 0
  },
  {
    "id": "status-2",
    "name": "In Progress",
    "position": 1
  },
  {
    "id": "status-3",
    "name": "Done",
    "position": 2
  }
]
```

The frontend must use the returned order.

---

# 9. Status Integrity

The API must reject a request where:

```text
task.project_id != task.status.project_id
```

For example, this must fail:

```text
Project A
    Task A
        Status from Project B
```

The backend must not trust a client-provided combination of project and status IDs.

---

# 10. Task Endpoints

Initial operations:

```http
POST  /api/projects/{project_id}/tasks
GET   /api/tasks/{task_id}
PATCH /api/tasks/{task_id}
```

A task created through:

```http
POST /api/projects/{project_id}/tasks
```

must belong to the specified project.

The service must verify that the selected status belongs to that project.

---

# 11. Task Creation

Example request:

```json
{
  "title": "Implement login page",
  "description": "Create the initial login form.",
  "status_id": "status-123",
  "assignee_id": "user-456"
}
```

The project is determined by the URL:

```text
/api/projects/{project_id}/tasks
```

The client should not be allowed to create a task in one project while specifying a status from another project.

---

# 12. Task Update

Task updates use:

```http
PATCH /api/tasks/{task_id}
```

Only fields supplied by the client should be changed.

Example:

```json
{
  "title": "Updated title",
  "status_id": "status-456"
}
```

If `status_id` changes, the backend must validate the project/status relationship.

---

# 13. Moving Tasks

Moving a task between Kanban columns is represented by changing its `ProjectStatus`.

Example:

```http
PATCH /api/tasks/{task_id}
```

```json
{
  "status_id": "status-456"
}
```

The backend validates:

```text
task.project_id == target_status.project_id
```

No separate Kanban-specific persistence operation is required for the basic MVP.

---

# 14. Status Reordering

Project status ordering is a project-level operation.

Example:

```http
POST /api/projects/{project_id}/statuses/reorder
```

Request:

```json
{
  "status_ids": [
    "status-3",
    "status-1",
    "status-2"
  ]
}
```

The backend must verify:

1. all supplied statuses belong to the project;
2. no status is duplicated;
3. no required status is omitted, if the API requires a complete ordering;
4. the operation is authorized;
5. the resulting ordering is persisted atomically.

---

# 15. Pagination

Collection endpoints should use explicit pagination.

The default pagination strategy should be offset/limit or cursor-based pagination depending on the resource.

For the MVP, a simple consistent strategy should be selected and used across collection endpoints.

Example:

```http
GET /api/projects/{project_id}/tasks?limit=50&offset=0
```

The API should define sensible maximum limits.

Clients must not be able to request unbounded result sets.

---

# 16. Filtering

Filtering uses query parameters for simple filters.

Example:

```http
GET /api/projects/{project_id}/tasks?status_id=status-1
```

Possible filters:

```text
status_id
assignee_id
reporter_id
task_type_id
priority
tag_id
```

Filters must be composable where practical.

---

# 17. Sorting

Sorting should be explicit.

Example:

```http
GET /api/projects/{project_id}/tasks?sort=updated_at
```

Supported sort fields must be defined by the endpoint.

Do not construct arbitrary SQL `ORDER BY` clauses directly from unvalidated client input.

---

# 18. Search

Simple task search may use:

```http
GET /api/projects/{project_id}/tasks?search=login
```

The search implementation may initially use PostgreSQL capabilities.

A full query language is explicitly out of MVP scope.

---

# 19. Saved Filters

Saved filters should expose structured filter data.

Example:

```json
{
  "name": "My active tasks",
  "filters": {
    "assignee_id": "current-user",
    "status_id": [
      "status-1",
      "status-2"
    ]
  }
}
```

The backend must validate the filter structure.

Do not store arbitrary SQL expressions from clients.

---

# 20. Comments

Initial API:

```http
POST /api/tasks/{task_id}/comments
GET  /api/tasks/{task_id}/comments
PATCH /api/comments/{comment_id}
DELETE /api/comments/{comment_id}
```

All operations must verify access to the underlying task.

---

# 21. Watchers

Initial API:

```http
GET    /api/tasks/{task_id}/watchers
POST   /api/tasks/{task_id}/watchers
DELETE /api/tasks/{task_id}/watchers/{user_id}
```

A user should normally be able to subscribe/unsubscribe themselves without exposing arbitrary organization membership changes.

---

# 22. Attachments

Initial API:

```http
POST /api/tasks/{task_id}/attachments
GET  /api/tasks/{task_id}/attachments
DELETE /api/attachments/{attachment_id}
```

File upload implementation may use multipart requests or pre-signed object-storage URLs.

The choice should be made based on the selected storage architecture.

---

# 23. Tags

Initial API:

```http
POST   /api/projects/{project_id}/tags
GET    /api/projects/{project_id}/tags
PATCH  /api/tags/{tag_id}
DELETE /api/tags/{tag_id}
```

Tasks may then reference project-local tags.

A tag from another project must not be attachable.

---

# 24. Notifications

Initial API:

```http
GET   /api/notifications
PATCH /api/notifications/{notification_id}
```

Possible operation:

```http
POST /api/notifications/read-all
```

Notifications must belong to the authenticated user.

---

# 25. Dashboard

The dashboard may expose aggregated project information.

Example:

```http
GET /api/projects/{project_id}/dashboard
```

The response should contain only data required by the UI.

Do not expose unrestricted database aggregation endpoints.

---

# 26. Response Schemas

Response objects should be explicit Pydantic models.

Example:

```python
class ProjectStatusResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    position: int
```

Do not return raw SQLAlchemy objects from route handlers.

---

# 27. Error Responses

The API should use a consistent error format.

Example:

```json
{
  "detail": {
    "code": "STATUS_PROJECT_MISMATCH",
    "message": "Status does not belong to the project."
  }
}
```

Validation errors may use FastAPI/Pydantic's standard validation structure.

Internal exception details must not be exposed.

---

# 28. Resource Not Found vs Unauthorized Access

The implementation must avoid leaking information about resources the user cannot access.

Where appropriate, an inaccessible resource may be represented as:

```text
404 Not Found
```

rather than revealing that the resource exists.

The exact behavior should be consistent across the API.

---

# 29. API Versioning

Do not introduce versioning complexity until it is required.

The initial API uses:

```text
/api/
```

If a breaking API evolution becomes necessary, document the migration strategy before introducing it.

---

# 30. OpenAPI

FastAPI automatically generates the OpenAPI specification.

The generated specification should be treated as a first-class development artifact.

Frontend API clients should use it as the contract.

API changes should update:

* request schemas;
* response schemas;
* endpoint behavior;
* tests;
* frontend client/types;
* documentation where necessary.

---

# 31. API Design Rules

1. Use nouns for resources.
2. Use HTTP methods according to operation semantics.
3. Keep routers thin.
4. Validate all external input.
5. Authorize every protected resource.
6. Never trust client-provided organization/project relationships.
7. Never trust a status ID without verifying its project.
8. Do not expose SQLAlchemy models directly.
9. Use pagination for collections.
10. Bound client-controlled limits.
11. Validate sorting fields.
12. Avoid arbitrary SQL expressions from API input.
13. Return stable error codes for domain errors where useful.
14. Keep API behavior consistent across resources.
15. Update tests and OpenAPI whenever behavior changes.


# 26. Membership and Resource Lifecycle

Organization and project membership endpoints require a bearer token. Membership writes are authorized by the corresponding owner. Adding an existing member again is idempotent and returns the current public user representation.

```http
GET    /api/organizations/{organization_id}/members
POST   /api/organizations/{organization_id}/members
DELETE /api/organizations/{organization_id}/members/{user_id}
POST   /api/organizations/{organization_id}/transfer-ownership
DELETE /api/organizations/{organization_id}
POST   /api/organizations/{organization_id}/restore
GET    /api/organizations/{organization_id}/projects

GET    /api/projects/{project_id}/members
POST   /api/projects/{project_id}/members
DELETE /api/projects/{project_id}/members/{user_id}
POST   /api/projects/{project_id}/transfer-ownership
DELETE /api/projects/{project_id}
POST   /api/projects/{project_id}/restore
```

Member mutation bodies identify an existing registered user by email:

```json
{
  "email": "user@example.com"
}
```

Deletion is soft and requires explicit confirmation:

```json
{
  "confirm": true
}
```

Organization deletion marks the organization and all its projects deleted. Restoration is separate: restoring an organization does not restore its projects, and a project cannot be restored while its organization is deleted. Deleted resources are hidden from ordinary list, retrieve, and mutation operations.

Organizations and projects expose `owner_id` and nullable `deleted_at` in their response representations.
