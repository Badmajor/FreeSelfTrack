

---
applyTo: "**/api/**/*.{py,ts,tsx},**/schemas/**/*.py,**/routes/**/*.py,**/routers/**/*.py"
---

# API Development Instructions

## API contract

The API contract must be explicit and predictable.

Backend is the source of truth.

Do not silently change an existing API contract.

Breaking API changes require an explicit task.

## REST

Use resource-oriented URLs.

Prefer:

```text
GET    /api/projects
POST   /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
````

Avoid action-oriented endpoints when a resource-oriented operation is possible.

Actions are acceptable when they represent a distinct domain operation, for example:

```text
POST /api/tasks/{task_id}/watchers
POST /api/tasks/{task_id}/status
```

## HTTP methods

Use:

* `GET` for retrieval;
* `POST` for creation/actions;
* `PATCH` for partial updates;
* `PUT` only when replacing a complete resource;
* `DELETE` for deletion/removal.

## HTTP status codes

Use appropriate status codes.

Typical responses:

```text
200 OK
201 Created
202 Accepted
204 No Content
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
422 Unprocessable Entity
429 Too Many Requests
500 Internal Server Error
```

Do not return `200 OK` for an operation that failed.

## Request validation

Validate all external input.

Use Pydantic schemas for FastAPI request/response models.

Do not trust:

* IDs;
* query parameters;
* headers;
* request bodies;
* file metadata.

## Response schemas

Every public endpoint should have an explicit response schema.

Do not expose SQLAlchemy models directly from API endpoints.

Do not accidentally expose internal fields.

## Authentication

Protected endpoints must explicitly enforce authentication.

Authorization must be checked separately from authentication.

Being authenticated does not imply access to a project or task.

## Authorization

For project/task resources verify:

1. user is authenticated;
2. user belongs to the relevant organization;
3. user has access to the project;
4. user has the required permission.

Do not rely on frontend authorization.

## Errors

Use consistent error responses.

Do not expose:

* stack traces;
* SQL queries;
* internal filesystem paths;
* secrets;
* infrastructure details.

## Pagination

Collection endpoints expected to return many records must support pagination.

Do not return an unbounded number of database records.

## Filtering

Filtering must be implemented server-side for potentially large datasets.

Do not download the entire dataset to the frontend just to filter it.

## Sorting

Sorting of large collections should be performed by the backend/database.

## API documentation

Every public endpoint must be represented correctly in OpenAPI.

Document:

* parameters;
* request body;
* response;
* authentication requirements;
* possible errors.

## API changes

When changing an API:

1. update backend schema;
2. update OpenAPI;
3. update generated frontend client/types if applicable;
4. update tests;
5. update documentation if necessary.

Never modify generated API files manually if they are regenerated from OpenAPI.
