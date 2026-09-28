# TASK-006: Containerized self-hosted deployment

## Goal

Create a Docker Compose deployment that starts the complete project and all required infrastructure services in containers with one command.

After `docker compose up --build`, a developer or self-hosting user must be able to open the frontend, use the backend API, connect to the exposed PostgreSQL instance, and keep data across container restarts.

---

## Context

The product is self-hosted first and Docker Compose is the documented deployment target.

The architecture is a modular monolith:

* the backend remains one FastAPI application and one application container;
* PostgreSQL remains the authoritative relational database;
* Redis is an infrastructure service for ephemeral and coordination workloads;
* MinIO provides the local S3-compatible object-storage implementation;
* the frontend is built and served from its own container.

This task is deployment and infrastructure work. It must not introduce microservices or split the backend domain into separate application services.

References:

* `docs/product/requirements.md`
* `docs/product/glossary.md`
* `docs/architecture/overview.md`
* `docs/architecture/api.md`
* `docs/architecture/decisions/001-modular-monolith.md`

---

## Requirements

### Functional requirements

* Provide a root-level `docker-compose.yml` or `compose.yml`.
* Start the complete project with:
  ```bash
  docker compose up --build
  ```
* Start the backend application container.
* Build and start the frontend container.
* Start PostgreSQL with a persistent named volume.
* Start Redis with a persistent named volume when persistence is configured.
* Start MinIO with a persistent named volume for the local S3-compatible storage.
* Run Alembic migrations automatically before the backend accepts traffic.
* Make the frontend available through a host port.
* Make PostgreSQL available through a host port.
* Keep backend, Redis, and MinIO application ports internal unless a concrete development need requires an external binding.
* Allow the frontend to call the backend through a stable same-origin `/api` route or an explicitly configured API URL.
* Ensure all services communicate through a dedicated Compose network.
* Provide healthchecks and startup dependencies so the backend does not start before its required dependencies are ready.
* Preserve service data across `docker compose down` and subsequent `up` runs unless volumes are explicitly removed.

### Technical requirements

* Use multi-stage builds where they reduce the runtime image.
* Run containers as a non-root user where practical.
* Pin base image major versions and document image/runtime choices.
* Do not copy local virtual environments, `node_modules`, caches, secrets, or build artifacts into images.
* Use `.dockerignore` files for backend and frontend build contexts.
* Configure services through environment variables and an example environment file.
* Never commit passwords, access tokens, private keys, or production credentials.
* Use Docker healthchecks instead of fixed sleep delays.
* Log useful startup failures without exposing secrets.
* Keep database migrations in the backend image and make startup migration execution idempotent.
* Do not use Redis or MinIO as the source of truth for relational domain data.

### Required services

| Service | Responsibility | External port |
| --- | --- | --- |
| `frontend` | Build and serve the React application | Yes, configurable |
| `backend` | Serve FastAPI and run migrations | No, internal by default |
| `db` | PostgreSQL persistence | Yes, configurable |
| `redis` | Cache, ephemeral state, and coordination | No |
| `minio` | Local S3-compatible object storage | No by default |

If the implementation discovers that a listed service is not yet consumed by application code, it must still either provision it with a documented purpose or explicitly record why it is deferred. Do not add unrelated infrastructure speculatively.

---

## Acceptance Criteria

The task is complete when:

* [x] A clean checkout can start the complete stack with `docker compose up --build`.
* [x] `docker compose config` succeeds without undefined variables or invalid references.
* [x] All required services are defined in Compose.
* [x] The backend image builds and starts successfully.
* [x] The frontend image builds and starts successfully.
* [x] PostgreSQL starts with a persistent named volume.
* [x] Redis starts and is reachable from the backend network.
* [x] MinIO starts with persistent storage and is reachable from the backend network.
* [x] PostgreSQL migrations run automatically and are idempotent.
* [x] Backend healthcheck becomes healthy after database dependencies are ready.
* [x] Frontend healthcheck or HTTP smoke check succeeds.
* [x] The frontend is reachable through the documented external port.
* [x] PostgreSQL is reachable through the documented external host port.
* [x] The frontend can call the backend API through the containerized deployment.
* [x] `POST /api/auth/register` and `POST /api/auth/login` work through the containerized stack.
* [x] A protected API request with a valid bearer token works through the containerized stack.
* [x] Restarting the stack preserves PostgreSQL data.
* [x] Restarting the stack preserves MinIO data.
* [x] Backend, Redis, and MinIO are not unnecessarily exposed on host ports.
* [x] No production secrets are present in Compose files, Dockerfiles, image layers, or committed example files.
* [x] Startup and failure behavior is documented for developers and self-hosting users.

---

## Domain

This task does not introduce domain entities or change business invariants.

Relevant invariants remain:

* PostgreSQL is the authoritative store for persistent domain data.
* The backend remains the source of truth for authentication, authorization, validation, and workflow.
* `task.project_id == task.status.project_id` remains enforced by the backend and database.
* Container boundaries must not bypass organization, project, or object-level authorization.

---

## Architecture

Affected areas:

* Docker Compose orchestration.
* Backend Dockerfile and startup command.
* Frontend Dockerfile and static asset serving.
* PostgreSQL, Redis, and MinIO service configuration.
* Runtime environment configuration.
* Local development and self-hosted deployment documentation.
* CI/container smoke tests.

Expected runtime topology:

```text
Browser
  |
  | external frontend port
  v
frontend container (static files + /api reverse proxy)
  |
  | internal Compose network
  v
backend container (FastAPI + Alembic)
  |             |             |
  v             v             v
PostgreSQL     Redis         MinIO
  |
  | named persistent volume
  v
database data
```

The backend remains a modular monolith inside one application container. PostgreSQL, Redis, and MinIO are infrastructure containers, not domain microservices.

---

## API

This task does not introduce new API endpoints.

The existing API must remain reachable through the containerized frontend/backend path:

```http
POST /api/auth/register
POST /api/auth/login
GET  /api/organizations
```

The frontend must use the same API base path in local development and in the Compose deployment, or document the required environment override.

### Errors

* Backend dependency failure must result in a clear unhealthy status or startup failure.
* The frontend must not silently display a working shell when its API configuration is invalid.
* Container logs must not expose database passwords, JWT secrets, or object-storage credentials.

---

## Database

### Changes

No new domain tables are required.

The deployment must:

* run the existing Alembic migration chain;
* use a dedicated PostgreSQL database and user configured through environment variables;
* persist PostgreSQL data in a named volume;
* expose the database through a configurable host port;
* avoid destructive initialization on normal startup;
* provide a healthcheck using PostgreSQL readiness.

### Migration

A new Alembic migration is required:

* [ ] Yes
* [x] No

Migration considerations:

* Do not modify existing migrations.
* A fresh PostgreSQL volume must be migratable from an empty database.
* Re-running backend startup must not fail because migrations are already applied.
* Removing volumes is the explicit destructive action that resets local data.

---

## Authorization

Docker networking must not weaken application authorization.

* Public frontend access must still go through backend authentication.
* Backend authorization remains responsible for organization, project, and object-level boundaries.
* Internal network reachability is not an authorization grant.
* Database and infrastructure credentials must be passed through environment configuration, not source code.
* Host port exposure must be limited to frontend and PostgreSQL as required by this task.

---

## Frontend

The frontend deployment must:

* build the React/Vite application in a builder stage;
* serve production assets from a small runtime image;
* route API requests to the backend container or use a documented API URL;
* expose a configurable host port, defaulting to the documented frontend port;
* provide a useful HTTP health/smoke endpoint;
* handle backend-unavailable startup and request errors visibly;
* avoid embedding secrets in browser assets.

The local development workflow must remain available outside Docker.

---

## Tests

### Backend and infrastructure

* [x] Compose configuration test with `docker compose config`.
* [x] Backend image build test.
* [x] Frontend image build test.
* [x] Fresh-volume migration smoke test.
* [x] Backend healthcheck test.
* [x] PostgreSQL host-port connectivity test.
* [x] Redis internal connectivity test.
* [x] MinIO internal connectivity test.
* [x] Containerized registration and login API test.
* [x] Containerized protected API request test.
* [x] Restart persistence test for PostgreSQL.
* [x] Restart persistence test for MinIO.

### Frontend

* [x] HTTP smoke test for the served frontend.
* [x] Frontend-to-backend API proxy smoke test.
* [x] Production frontend build and typecheck.

### Regression

* [x] Existing local workflows remain represented by the existing backend/frontend checks; host toolchains were unavailable in this shell, so production builds were validated in Docker.

Specific scenarios:

* [x] Start from empty volumes and reach a healthy stack.
* [x] Register and log in through the frontend origin.
* [x] Stop and start the stack without losing a registered user.
* [x] Verify PostgreSQL is reachable on the documented host port.
* [x] Verify Redis and MinIO are reachable only from the Compose network by default.
* [x] Run migrations twice without failure.
* [x] Bring down only the backend and verify the frontend reports API failure clearly.
* [x] Remove volumes explicitly and verify the stack can initialize again from scratch.

---

## Dependencies

* `TASK-001` — core backend domain and migrations.
* `TASK-002` — authentication API and frontend authentication flow.
* Existing backend and frontend build configurations.

---

## Validation

Run from the repository root:

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs backend
docker compose down
```

Run the application smoke checks:

```bash
curl -I http://localhost:5173
curl -i http://localhost:5173/api/auth/login
pg_isready -h localhost -p 5432
```

Run existing application checks:

```bash
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy app

cd ../frontend
npm run typecheck
npm run build
```

The final validation must include a clean-volume run and a restart/persistence run.

---

## Definition of Done

* [ ] Compose file implemented.
* [ ] Backend container implemented.
* [ ] Frontend container implemented.
* [ ] PostgreSQL container and persistent volume implemented.
* [ ] Redis container implemented.
* [ ] MinIO container and persistent volume implemented.
* [ ] Frontend host port documented and working.
* [ ] PostgreSQL host port documented and working.
* [ ] Backend migrations run automatically and safely.
* [ ] Healthchecks and startup dependencies implemented.
* [ ] Environment example and secret handling documented.
* [ ] Compose smoke and persistence tests added.
* [ ] Existing backend/frontend tests still pass.
* [ ] Deployment documentation updated.
* [ ] Final diff reviewed.
* [ ] No unrelated changes introduced.

---

## Implementation Notes

* Keep the default Compose topology simple enough for local self-hosting.
* Prefer a frontend reverse proxy for same-origin `/api` requests so browser configuration does not depend on container-internal hostnames.
* Do not publish Redis, MinIO, or the backend unless a documented development workflow requires it.
* If MinIO or Redis is not consumed by the current application code, document the provisioned integration boundary instead of inventing application behavior.
* If the complete stack requires a durable architectural choice, create an ADR before implementation.

---

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

* None
