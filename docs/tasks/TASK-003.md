# TASK-003: Project membership and authorization

## Goal

Implement organization and project membership management so authenticated users can safely access only the organizations and projects they belong to, while project owners can manage project members.

## Context

The MVP already has users, organizations, projects, `OrganizationMember`, and `ProjectMember` records. Organization and project creation automatically adds the creator as a member, but there is no API for managing membership and no explicit project-management permission.

This task establishes the authorization boundary required before expanding the project, Kanban, and task workflows. Authorization remains server-side and the frontend must not be treated as a security boundary.

References:

* `docs/product/requirements.md`
* `docs/product/glossary.md`
* `docs/architecture/overview.md`
* `docs/architecture/api.md`
* `docs/architecture/decisions/004-membership-ownership-lifecycle.md`

## Requirements

### Functional requirements

* An authenticated user can list the organizations they belong to.
* An organization member can list the organization's projects.
* An organization owner can add an existing user to the organization by email and remove a member, subject to the owner-removal rule.
* An organization owner can transfer organization ownership to another organization member by email.
* An organization owner can explicitly soft-delete the organization and all its projects after a destructive-action warning and confirmation.
* An organization owner can restore a soft-deleted organization.
* A project owner can restore a soft-deleted project.
* Restoring an organization does not automatically restore its projects; each project is restored separately.
* A project cannot be restored while its organization is soft-deleted.
* A project creator is recorded as the project owner.
* A project owner can list, add, and remove project members.
* A project owner can explicitly soft-delete the project through a dedicated endpoint.
* A project owner can transfer project ownership to another project member by email.
* A project member can access the project and its authorized resources.
* A project member can be added only when they belong to the project's organization.
* Removing a project member revokes access to that project without deleting the user or their organization membership.
* Repeated membership operations are idempotent: the existing membership is returned and no duplicate row is created.

### Technical requirements

* Enforce organization and project boundaries in backend services/repositories, not in routers or frontend code.
* Use `401 Unauthorized` for missing/invalid authentication and `403 Forbidden` for an authenticated user without permission.
* Avoid IDOR: every organization, project, member, status, and task lookup must verify the current user's access context.
* Preserve the invariant that a project belongs to exactly one organization and a project member belongs to that organization.
* Keep membership mutations transactional and protected by database uniqueness constraints.
* Do not introduce invitations, email delivery, teams, or speculative permission hierarchies in this task.

## Acceptance Criteria

* [x] An authenticated user can list only organizations where they are a member.
* [x] An authenticated user cannot retrieve another organization's data by changing its ID.
* [x] An organization owner can add an existing user to the organization.
* [x] A non-owner organization member receives `403` when managing organization membership.
* [x] `POST /api/organizations/{organization_id}/transfer-ownership` transfers ownership to an existing organization member identified by email.
* [x] A sole organization owner receives a warning that the organization and all its projects will be deleted, and deletion requires explicit confirmation.
* [x] An organization member can list projects in that organization.
* [x] A user who is not an organization member cannot access its projects.
* [x] The project creator is persisted as the project owner.
* [x] A project owner can list, add, and remove project members.
* [x] A non-owner project member receives `403` when managing project membership.
* [x] A user from another organization cannot be added to the project.
* [x] A removed project member receives `403` or `404` when accessing the project and its resources.
* [x] The project owner cannot remove themselves without transferring ownership.
* [x] A project owner receives a destructive-action warning before soft-deleting a project with any number of members, and the project is not deleted without `{"confirm": true}`.
* [x] An organization owner receives a clear cascade soft-delete warning and the organization is not deleted without `{"confirm": true}`.
* [x] `POST /api/organizations/{organization_id}/restore` restores a soft-deleted organization.
* [x] `POST /api/projects/{project_id}/restore` restores a soft-deleted project.
* [x] Restoring an organization leaves its soft-deleted projects unchanged until each project is restored separately.
* [x] Restoring a project while its organization is soft-deleted is rejected.
* [x] `DELETE /api/projects/{project_id}` soft-deletes the project only for its owner and only when the request body contains `{"confirm": true}`.
* [x] `POST /api/projects/{project_id}/transfer-ownership` transfers ownership to an existing project member identified by email.
* [x] Repeated membership creation does not create duplicate rows and returns the existing membership successfully.
* [x] Missing, malformed, expired, and invalid bearer tokens return `401`.
* [x] Existing authentication and task/status authorization tests remain green.

## Domain

Relevant entities:

* `User`
* `Organization`
* `OrganizationMember`
* `Project`
* `ProjectMember`

Relevant invariants:

* An organization member references an existing user and organization.
* A project belongs to exactly one organization.
* A project member must also be a member of the project's organization.
* A project has exactly one owner; the owner cannot leave or be removed until ownership is transferred. If the owner is the only project member, leaving is replaced by an explicit project-deletion confirmation flow.
* Membership rows are unique by `(organization_id, user_id)` and `(project_id, user_id)`.
* Organization and project resources are never accessible solely because a caller knows an object ID.

## Architecture

Affected areas:

* Backend models and repositories for membership queries.
* Backend services for membership mutations and authorization policies.
* FastAPI routers and Pydantic request/response schemas.
* Alembic migration for ownership/role data and missing foreign keys or constraints.
* Frontend project/member views and API client integration.
* Backend and API authorization tests.

The implementation must preserve the existing flow:

```text
HTTP request -> schema -> authentication -> authorization -> service -> repository -> database
```

## API

### Organization membership

```http
GET    /api/organizations/{organization_id}/members
POST   /api/organizations/{organization_id}/members
DELETE /api/organizations/{organization_id}/members/{user_id}
POST   /api/organizations/{organization_id}/transfer-ownership
DELETE /api/organizations/{organization_id}
POST   /api/organizations/{organization_id}/restore
GET    /api/organizations/{organization_id}/projects
```

Example request:

```json
{
  "email": "user@example.com"
}
```

### Project membership

```http
GET    /api/projects/{project_id}/members
POST   /api/projects/{project_id}/members
DELETE /api/projects/{project_id}/members/{user_id}
DELETE /api/projects/{project_id}
POST   /api/projects/{project_id}/restore
POST   /api/projects/{project_id}/transfer-ownership
```

Destructive delete requests use the following body and require `confirm: true`:

```json
{
  "confirm": true
}
```

The same confirmation contract applies to project and organization deletion.

Responses must expose public user/member data only. They must not expose password hashes, access tokens, or other credentials.

### Errors

* `401 Unauthorized` — missing or invalid bearer token.
* `403 Forbidden` — authenticated user lacks organization/project management permission.
* `404 Not Found` — resource is not visible in the caller's authorization context; use this where hiding resource existence is required.
* `409 Conflict` — an attempt to remove an owner or another state transition that cannot be completed.
* Confirmed organization deletion cascades to its projects and project-owned resources according to the domain retention policy.
* Ownership transfer must reject a user who is not already a project member.
* `422 Unprocessable Entity` — invalid UUID or malformed request body.

The final endpoint names and response schemas must be reflected in `docs/architecture/api.md` when implemented.

## Database

### Changes

Inspect the existing schema before migration. The implementation is expected to:

* add explicit foreign keys from membership `user_id` columns to `users.id`;
* add `owner_id` foreign keys for organizations and projects; do not model ownership as a membership role;
* add a soft-delete timestamp/flag for organizations and projects with indexes or query helpers as needed;
* preserve unique membership constraints;
* add indexes for organization/project membership lookups;
* define explicit `ON DELETE` behavior; soft-deleted organizations and projects retain membership, statuses, and tasks, but these records are excluded from normal access and list queries.

### Migration

A new Alembic migration is required:

* [x] Yes
* [ ] No

Migration considerations:

* Existing organizations and projects need a deterministic owner backfill.
* Existing creator memberships should be promoted to owner where possible.
* The migration must work on a fresh database and on an existing TASK-001/TASK-002 database.
* Do not modify an already-applied migration.

## Authorization

* Every endpoint requires an authenticated active user.
* Organization membership grants access to that organization's projects, but not to unrelated organizations.
* Project membership grants access to project resources.
* Only the organization owner may manage organization membership.
* Only the project owner may manage project membership.
* A project member cannot grant access to a user outside the project's organization.
* Removing the project owner is forbidden until ownership is transferred. When the owner is the sole project member, the UI must warn that the project will be deleted and require explicit confirmation before deletion.
* Authorization checks must be performed in the service/repository path for every object-level operation.

## Frontend

Implement the minimum UI needed to consume the API:

* project members list;
* add-member form using an existing user's email;
* remove-member action visible only to project owners;
* loading, empty, validation, unauthorized, and server-error states;
* refresh the server state after membership mutations.

The frontend must not hide unauthorized actions as the only protection; the backend remains authoritative.

## Tests

### Backend

* [x] Unit tests for membership services and owner rules.
* [x] API tests for listing, adding, and removing organization members.
* [x] API tests for listing, adding, and removing project members.
* [x] Authorization tests for `401`, `403`, `404`, and `409` cases.
* [x] Organization isolation tests.
* [x] Project isolation tests.
* [x] Idempotent membership, ownership-transfer, soft-delete, restore, and owner-removal tests.
* [x] Migration test with existing users, organizations, projects, and memberships.

### Frontend

* [ ] Component tests for member list and mutation states.
* [x] Interaction tests for owner-only controls and API errors.

### Regression

* [x] Registration and login remain unchanged.
* [x] Existing organization, project, status, and task endpoints preserve their authorization behavior.

## Dependencies

* `TASK-001` — core task domain.
* `TASK-002` — authentication.
* `TASK-006` — containerized development and PostgreSQL environment.

## Validation

```bash
# Backend
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app

# Frontend
cd ../frontend
npm run typecheck
npm run build

# API/container smoke checks
cd ..
docker compose config
docker compose up -d --build
```

## Definition of Done

* [x] Requirements implemented.
* [x] Acceptance criteria satisfied.
* [x] Domain invariants preserved.
* [x] Authorization implemented and tested.
* [x] Database migration created and verified, including soft-delete behavior.
* [x] API contract updated.
* [x] Frontend member workflow implemented.
* [x] Relevant tests added or updated.
* [x] Relevant validation passed.
* [x] Documentation updated.
* [x] Final diff reviewed.
* [x] No unrelated changes introduced.

## Implementation Notes

* Keep the first permission model small: organization owner and project owner are sufficient for this task.
* Do not add an invitation/email delivery subsystem; membership management operates on existing registered users found by email.
* Ownership is represented by separate `owner_id` foreign keys on organizations and projects.
* An owner cannot leave their project without transferring ownership; project deletion always requires an explicit confirmation operation.
* Project ownership transfer targets an existing project member identified by email.
* If the ownership model requires a durable architectural decision, add an ADR under `docs/architecture/decisions/` before implementation.

## Status

* Status: DONE
* Started: 2026-09-28
* Completed: 2026-09-28

### Progress

* [x] Analysis
* [x] Implementation
* [x] Tests
* [x] Validation
* [x] Review

### Known issues

* Frontend component tests remain a follow-up because the frontend has no test runner configured; production build and Compose HTTP smoke tests pass.
