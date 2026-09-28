# Development Setup

## Docker Compose

Docker Compose starts the complete local stack:

- frontend at `http://localhost:5173`;
- backend API through the frontend at `http://localhost:5173/api`;
- PostgreSQL on `127.0.0.1:5432`;
- Redis and MinIO on the internal Compose network.

Prepare local variables and start the stack:

```bash
cp .env.example .env
docker compose up --build
```

The backend applies Alembic migrations before starting. Startup dependencies use healthchecks, so the API waits for PostgreSQL, Redis, and MinIO. The database, Redis AOF, and MinIO data are stored in named volumes.

Useful commands:

```bash
docker compose ps
docker compose logs -f backend
docker compose down
docker compose down -v  # removes local data volumes
```

Set `FRONTEND_PORT` or `POSTGRES_PORT` in `.env` when the default host ports are busy. Keep `AUTH_SECRET_KEY`, database credentials, and MinIO credentials overridden with strong values outside local development.

## Local processes

Backend development uses `uv` from `backend/`; set `TRACKER_DATABASE_URL` in the backend environment before starting it directly. The Compose backend receives its internal `db:5432` URL from environment variables; the published PostgreSQL host port is only for external debugging. Frontend development uses npm from `frontend/`. The Vite dev server proxies `/api` to `http://localhost:8000`, matching the same-origin URL used by the Compose frontend.
