# TASK-002: User registration and authentication

## Goal

Implement user registration and login so a person can create an account and obtain authenticated access to the system.

---

## Context

The product requires an authenticated user before organization and project operations are available.

TASK-001 currently uses a temporary `X-User-ID` identity adapter. This task introduces a User model and authentication flow that becomes the source of the current user identity.

References:

* docs/product/requirements.md
* docs/product/glossary.md
* docs/architecture/api.md
* docs/architecture/overview.md

---

## Requirements

### Functional requirements

* Provide public registration by email and password.
* Normalize email consistently before persistence and lookup.
* Reject registration when the normalized email is already registered.
* Validate passwords at the API boundary.
* Store only a password hash; never store or return plaintext passwords.
* Authenticate a registered user by email and password.
* Return an access token after successful login.
* Reject invalid credentials without revealing whether the email exists.
* Derive the current user in protected endpoints from the verified token.
* Replace the temporary `X-User-ID` identity mechanism from TASK-001.

### Technical requirements

* Use an explicit SQLAlchemy `User` model.
* Use explicit Pydantic request and response schemas.
* Use a maintained password hashing library; Argon2id is preferred.
* Store email in canonical form and enforce uniqueness in the database.
* Do not log passwords, password hashes, access tokens, or other credentials.
* Keep authentication in dependencies and services; routers remain thin.
* Keep existing organization and project authorization checks.

### Out of scope

* Email verification.
* Password reset or change-password flows.
* OAuth or social login.
* Multi-factor authentication.
* Refresh tokens and session revocation unless required by the selected token implementation.
* Organization invitations and project membership management.

---

## Acceptance Criteria

The task is complete when:

* [x] A user can register with a valid email and password.
* [x] Registration creates exactly one User record.
* [x] Email uniqueness is enforced case-insensitively after normalization.
* [x] Invalid email input is rejected consistently.
* [x] Passwords shorter than 8 characters are rejected.
* [x] Passwords longer than 128 characters are rejected.
* [x] The stored value is a password hash and never the plaintext password.
* [x] Duplicate email registration returns 409 Conflict.
* [x] A registered user can log in with valid credentials.
* [x] Invalid credentials return 401 Unauthorized without account enumeration.
* [x] Successful login returns an access token and minimal user data.
* [x] Protected endpoints derive the current user from the access token.
* [x] Missing or invalid tokens return 401 Unauthorized.
* [x] Existing organization and project authorization boundaries remain enforced.
* [x] API schemas do not expose password or password_hash.
* [x] Frontend forms handle loading, validation, success, and server errors.

---

## Domain

### Entity

* `User`

Required fields:

* `id`
* `email`
* `password_hash`
* `is_active`
* `created_at`
* `updated_at`

### Invariants

* User email is stored in canonical normalized form.
* No two users share the same normalized email.
* Plaintext passwords are never persisted or returned.
* An inactive user cannot authenticate.
* Authentication identifies a User but does not grant organization or project access.

---

## Architecture

Affected areas:

* Backend model, repository, service, dependency, and API layers.
* Database migration and email lookup index.
* Frontend authentication forms and API client.
* Protected endpoint authentication dependencies.
* Backend and frontend tests.

If token/session storage or authentication transport requires a lasting architectural choice, record it in an ADR.

---

## API

### Endpoints

```
POST /api/auth/register
POST /api/auth/login
```

### Register request

```
{
  "email": "user@example.com",
  "password": "correct horse battery staple"
}
```

### Register response

```
{
  "id": "user-uuid",
  "email": "user@example.com",
  "is_active": true,
  "created_at": "2026-09-27T12:00:00Z"
}
```

Registration must not return a password, password hash, or access token unless registration explicitly includes login.

### Login request

```
{
  "email": "user@example.com",
  "password": "correct horse battery staple"
}
```

### Login response

```
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

### Errors

* 400 Bad Request or 422 Unprocessable Entity for malformed input.
* 409 Conflict for an already registered email.
* 401 Unauthorized for invalid credentials, inactive users, missing tokens, or invalid tokens.
* Login errors must not disclose whether the email is registered.

The final token transport and claims must be documented in the API implementation and used consistently by protected endpoints.

---

## Database

Create a `users` table with:

* UUID primary key.
* Canonical email column.
* Password hash column.
* Active flag.
* Creation and update timestamps.
* Unique constraint on normalized email.
* Index supporting email lookup.

A new Alembic migration is required:

* [x] Yes
* [ ] No

The migration must preserve TASK-001 data and be reversible where practical.

---

## Authorization

Registration and login are public operations.

All organization, project, status, and task operations remain protected.

Authentication is not authorization:

* a valid token identifies the user;
* organization membership controls organization access;
* project membership controls project access;
* object-level checks prevent IDOR.

A forged or invalid token must never grant access.

---

## Frontend

Implement:

* Registration screen with email and password fields.
* Login screen with email and password fields.
* Centralized API client methods for registration and login.
* Authenticated token/session storage using the selected project mechanism.
* Redirect after successful login.
* Loading, field validation, and server error states.
* Accessible labels, focus behavior, and keyboard submission.

The frontend must not implement password hashing or replace backend validation.

---

## Tests

### Backend

* [x] Unit tests for email normalization and password validation.
* [x] Unit tests for password hashing and verification.
* [x] API test for successful registration.
* [x] API tests for malformed email and password boundaries.
* [x] API test for duplicate email with case differences.
* [x] API test proving plaintext password is not persisted or returned.
* [x] API test for successful login.
* [x] API test for invalid credentials and inactive user.
* [x] API tests for missing and invalid access tokens.
* [x] Regression tests for TASK-001 authorization with authenticated identity.

### Frontend

* [x] Component tests for registration and login forms.
* [x] Interaction tests for validation and submission states.
* [x] API/state tests for success and server errors.

### Regression scenarios

* [x] Register User A, log in, and create an organization.
* [x] Register USER@example.com after user@example.com exists.
* [x] Attempt login with an incorrect password.
* [x] Access an owned organization with a valid token.
* [x] Attempt to access another user's organization with a valid but unauthorized token.
* [x] Replace `X-User-ID` identity with token-based identity.

---

## Dependencies

* TASK-001 — core task domain and temporary identity integration.

---

## Validation

Run from `backend/`:

```
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run alembic upgrade head
```

Frontend validation must include linting, type-checking, and relevant tests.

---

## Definition of Done

* [x] User model and migration implemented.
* [x] Registration API implemented.
* [x] Login API implemented.
* [x] Password hashing and validation implemented.
* [x] Duplicate email protection implemented.
* [x] Token issuance and verification implemented.
* [x] Protected endpoints use authenticated user identity.
* [x] Frontend registration and login flows implemented.
* [x] Authorization regression tests pass.
* [x] API documentation is consistent.
* [x] Relevant tests and validation pass.
* [x] No credentials or tokens are logged or exposed.
* [x] Final diff reviewed.
* [x] No unrelated changes introduced.

---

## Implementation Notes

* Keep authentication replaceable behind a dependency so protected endpoints do not depend on token parsing details.
* Use one canonical authentication error for invalid login credentials.
* Do not add organization membership behavior beyond preserving TASK-001 authorization.

---

## Status

* Status: DONE
* Started: 2026-09-27
* Completed: 2026-09-27

### Progress

* [x] Analysis
* [x] Implementation
* [x] Tests
* [x] Validation
* [x] Review

### Known issues

* None

