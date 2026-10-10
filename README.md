[RU](README_RU.md)

# FreeSelfTrack

**FreeSelfTrack** is a free, self-hosted task tracker for teams and small organizations.

It allows you to run your own task management system on your own server and keep your data under your own control, without requiring a mandatory dependency on a cloud SaaS provider.

> **Project status:** Early development / MVP

## Table of Contents

- [Features](#features)
- [Why Self-Hosted?](#why-self-hosted)
- [Quick Start](#quick-start)
- [1. Requirements](#1-requirements)
- [2. Install Docker](#2-install-docker)
- [3. Download FreeSelfTrack](#3-download-freeselftrack)
- [4. Configure the Application](#4-configure-the-application)
- [Connect an SMTP Server](#connect-an-smtp-server)
- [5. Start FreeSelfTrack](#5-start-freeselftrack)
- [6. Open FreeSelfTrack](#6-open-freeselftrack)
- [7. First Login](#7-first-login)
- [Architecture](#architecture)
- [Attachments and Malware Scanning](#attachments-and-malware-scanning)
- [Data Storage](#data-storage)
- [Stop FreeSelfTrack](#stop-freeselftrack)
- [Completely Remove FreeSelfTrack](#completely-remove-freeselftrack)
- [Updating FreeSelfTrack](#updating-freeselftrack)
- [Viewing Logs](#viewing-logs)
- [Health Checks](#health-checks)
- [Using Your Own Domain](#using-your-own-domain)
- [Example Nginx Configuration](#example-nginx-configuration)
- [Security](#security)
- [Backups](#backups)
- [Changing the Port](#changing-the-port)
- [Local Development](#local-development)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [API](#api)
- [Current Limitations](#current-limitations)
- [Troubleshooting](#troubleshooting)
- [Removing FreeSelfTrack](#removing-freeselftrack)
- [Development](#development)
- [License](#license)
- [Author](#author)
- [Feedback](#feedback)

## Features

FreeSelfTrack is designed for managing projects, tasks, and team workflows.

Current features include:

* administrative user creation, temporary passwords and authentication;
* organizations;
* organization members;
* projects;
* project members;
* custom project statuses;
* Kanban boards;
* status reordering;
* tasks;
* task assignees;
* task priorities;
* task deadlines;
* comments;
* user mentions;
* task watchers;
* notifications;
* task history;
* file attachments in private MinIO storage with automatic ClamAV scanning;
* task management;
* organization and project restoration;
* background processing of deadline notifications.

### Kanban boards

Each project can have its own set of statuses.

For example:

```text
Backlog → To Do → In Progress → Review → Testing → Done
```

Statuses are not global. Different projects can use different workflows.

---

# Why Self-Hosted?

FreeSelfTrack can be installed on your own server.

This allows you to:

* keep control over your data;
* avoid depending on a SaaS provider;
* use your own domain;
* run the system inside a private network;
* perform your own backups;
* modify the source code to meet your requirements.

FreeSelfTrack does not require registration with an external cloud service for the application itself to work.

---

# Quick Start

The easiest way to run FreeSelfTrack is with Docker Compose.

For a standard installation, you do **not** need to install Python, Node.js, PostgreSQL, or Redis separately.

To run the containers, you need Docker with Docker Compose support. Account creation and password recovery are administrative operations and do not require SMTP.

## 1. Requirements

At minimum, you need:

* a Linux server;
* Docker;
* Docker Compose;
* SSH access to the server;
* an available TCP port for the web interface;
* administrator credentials (`ADMIN_EMAIL` and `ADMIN_PASSWORD`).

For a small team, you can start with approximately:

* 2 CPU cores;
* 2–4 GB RAM;
* 10+ GB of free disk space.

Actual requirements depend on the number of users, tasks, and attachments.

---

# 2. Install Docker

If Docker is not installed yet, install Docker Engine and Docker Compose according to the official Docker documentation.

Check the installation:

```bash
docker --version
docker compose version
```

Both commands should return the installed version.

---

# 3. Download FreeSelfTrack

Connect to your server via SSH.

Create a directory for the application:

```bash
sudo mkdir -p /opt/freeselftrack
sudo chown "$USER":"$USER" /opt/freeselftrack
```

Enter the directory:

```bash
cd /opt/freeselftrack
```

Clone the repository:

```bash
git clone https://github.com/Badmajor/FreeSelfTrack.git .
```

If Git is not installed:

```bash
sudo apt update
sudo apt install -y git
```

Then clone the repository:

```bash
git clone https://github.com/Badmajor/FreeSelfTrack.git .
```

---

# 4. Configure the Application

The repository contains an `.env.example` file.

Create your local configuration:

```bash
cp .env.example .env
```

Open the file:

```bash
nano .env
```

At minimum, change the passwords and application secret, set administrator credentials, and set `PUBLIC_APP_URL` and `PUBLIC_HOST`. The example below is for local use; for a server, use HTTPS and the settings in the custom-domain section.

Example:

```env
POSTGRES_DB=tracker
POSTGRES_USER=tracker
POSTGRES_PASSWORD=CHANGE_THIS_DATABASE_PASSWORD

POSTGRES_BIND_ADDRESS=127.0.0.1
POSTGRES_PORT=5431

TRACKER_DATABASE_URL=postgresql+asyncpg://tracker:CHANGE_THIS_DATABASE_PASSWORD@db:5432/tracker

AUTH_SECRET_KEY=

DEADLINE_WORKER_INTERVAL_SECONDS=60

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=CHANGE_THIS_MINIO_PASSWORD
S3_BUCKET=tracker-attachments
ATTACHMENT_UPLOAD_SLOTS=2
ATTACHMENT_DOWNLOAD_SLOTS=4
ATTACHMENT_SCAN_INTERVAL_SECONDS=5
ATTACHMENT_SCAN_TIMEOUT_SECONDS=60

FRONTEND_BIND_ADDRESS=127.0.0.1
FRONTEND_PORT=5173

PUBLIC_APP_URL=http://localhost:5173
PUBLIC_HOST=localhost
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=YOUR_SMTP_USERNAME
SMTP_PASSWORD=YOUR_SMTP_PASSWORD
SMTP_SENDER=noreply@example.com
```

`PUBLIC_APP_URL` is an exact origin: scheme, hostname and port if nonstandard, without a
path, trailing `/`, query or fragment. It is used for email links, CORS and CSRF checks.
`PUBLIC_HOST` is the hostname only, without scheme or port; it permits requests to frontend
nginx. For local use, open exactly `http://localhost:5173`.

## Connect an SMTP Server

SMTP is not used for account creation or password recovery. The settings below are reserved for email-change delivery (TASK-036); that flow is not implemented yet.

| Variable | Value |
| --- | --- |
| `PUBLIC_APP_URL` | Frontend address reachable by users, such as `https://tasks.example.com`. Confirmation links use this address. Use `localhost` only for local development. |
| `SMTP_HOST` | SMTP hostname or address reachable from the container. `localhost` inside the worker refers to that container itself. |
| `SMTP_PORT` | SMTP port: usually `587` for STARTTLS or `465` for TLS. |
| `SMTP_SECURITY` | `starttls` for STARTTLS or `tls` for TLS from the start of the connection. Use `plain` only with an isolated local test mail server. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Credentials supplied by your email provider; use an app password if required. Leave both empty for a server that requires no authentication. |
| `SMTP_SENDER` | Sender email address authorized by your SMTP server. |

Replace the example values in `.env` with your settings. Both `starttls` and `tls` verify the server certificate. Do not publish `.env` containing mail credentials.

Compose retains the `registration-mail-worker` service for expired-session cleanup. It no longer sends registration or password-reset messages.

## Important

Do not use example passwords on a server that is accessible from the Internet.

In particular, change:

```env
POSTGRES_PASSWORD
AUTH_SECRET_KEY
MINIO_ROOT_PASSWORD
```

`AUTH_SECRET_KEY` is required. Startup rejects weak and placeholder values; there is no fallback.

You can generate one with:

```bash
openssl rand -hex 32
```

Then use the generated value:

```env
AUTH_SECRET_KEY=your-generated-value
```

---

# 5. Start FreeSelfTrack

After configuring `.env`, run:

```bash
docker compose up -d --build
```

Docker will download the required base images and build the application containers.

Check the container status:

```bash
docker compose ps
```

The main services should be running.

---

# 6. Open FreeSelfTrack

By default, the web interface binds to `127.0.0.1:5173` on the Docker host and is not directly reachable remotely.

If FreeSelfTrack is running on your local computer:

```text
http://localhost:5173
```

If it is installed on a server:

```text
https://tasks.example.com
```

Configure an HTTPS reverse proxy and set `PUBLIC_APP_URL=https://tasks.example.com` and `PUBLIC_HOST=tasks.example.com`.
The bundled frontend listens on HTTP internally; do not use remote plain HTTP for login.

---

# 7. First Login

Open FreeSelfTrack in your browser.

1. Sign in with the deployment's ADMIN_EMAIL and ADMIN_PASSWORD.
2. Open **Users** and create an account; share its one-time displayed temporary password securely.
3. The new user signs in, sets a permanent password, and signs in again.

The temporary password has no expiry, but cannot grant workspace access before password change.
Existing users retain their passwords. Public registration and email recovery are disabled.

After signing in as system administrator, you can create an organization:

```text
Organization
    ↓
Project
    ↓
Statuses
    ↓
Tasks
```

For example:

```text
My Company

    Website Development

        Backlog
        To Do
        In Progress
        Review
        Done

            TASK-1
            TASK-2
            TASK-3
```

---

# Architecture

The standard Docker Compose installation runs several containers.

```text
                         Internet
                            │
                     HTTPS proxy :443
                     (on Docker host)
                            │
                            ▼
                   ┌─────────────────┐
                   │    Frontend     │
                   │     nginx       │
                   │ 127.0.0.1:5173  │
                   └────────┬────────┘
                            │
                            │ /api/*
                            ▼
                   ┌─────────────────┐
                   │     Backend     │
                   │     FastAPI     │
                   │      :8000      │
                   └───────┬─┬───────┘
                           │ │
               ┌───────────┘ └───────────┐
               ▼                         ▼
       ┌──────────────┐          ┌──────────────┐
       │  PostgreSQL  │          │    Redis     │
       │     :5432    │          │     :6379    │
       └──────────────┘          └──────────────┘
```

The backend stores attachment metadata in PostgreSQL and file bytes in private MinIO storage.
A separate worker reads files from MinIO and scans them with ClamAV before release.

```text
Backend ──► MinIO ◄── attachment-scan-worker ──► ClamAV
                ▲              │
attachment-cleanup-worker      └──► PostgreSQL
```

## Services

### Frontend

A React application built into static files and served by nginx.

### Backend

A FastAPI-based API responsible for:

* users;
* organizations;
* projects;
* tasks;
* statuses;
* comments;
* notifications;
* task history;
* authentication.

### PostgreSQL

The main application database.

### Redis

Used by the application for auxiliary operations and background processing.

### Deadline Worker

A background worker that periodically checks task deadlines and creates corresponding notifications.

### Registration Mail Worker

The `registration-mail-worker` container now cleans expired sessions. Registration/reset mail is disabled.

---

# Attachments and Malware Scanning

MinIO stores all attachment bytes. Its native startup creates `S3_BUCKET` (default
`tracker-attachments`) through `MINIO_DEFAULT_BUCKETS`. The backend and workers use the
configured `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`. No provisioning container is needed;
MinIO and ClamAV are not exposed externally.

Compose automatically starts:

* `clamav` — the antivirus engine; FreshClam updates signatures in `clamav_data`;
* `attachment-scan-worker` — verifies size, SHA-256, image validity and the ClamAV verdict;
* `attachment-cleanup-worker` — removes unreferenced objects and abandoned multipart uploads.

Uploads start as `pending`. Only a clean verdict changes them to `ready`, permitting download
with task access checks. `infected` and `failed` files remain unavailable; encrypted archives
and scan-limit alerts are also blocked. Scanner or storage outages leave files `pending`
for retry. Chat updates availability automatically. Previews use a download queue with retries
for HTTP 429.

Limits: 25 MiB per file, five files and 130 MiB per request, and 40 million decoded pixels
across image frames. By default, each backend process permits two concurrent uploads and
four downloads. Scanning pauses five seconds between passes; ClamAV requests time out after
60 seconds. These settings are listed in `.env.example`.

The scan worker waits for ClamAV readiness on startup. Allow additional memory for the engine
and signatures, and outbound access for signature updates. Antivirus scanning cannot guarantee
detection of every threat.

See [attachment operations](docs/development/attachments.md) for details.

---

# Data Storage

The Docker Compose configuration uses named Docker volumes.

The main volumes are:

```text
postgres_data
redis_data
minio_data
clamav_data
```

List Docker volumes:

```bash
docker volume ls
```

Stopping the application does **not** remove these volumes:

```bash
docker compose down
```

After starting the application again:

```bash
docker compose up -d
```

the data should remain available.

---

# Stop FreeSelfTrack

To stop the application:

```bash
docker compose down
```

This stops and removes the containers but does not remove Docker volumes.

To start it again:

```bash
docker compose up -d
```

---

# Completely Remove FreeSelfTrack

If you want to remove the application together with its stored data:

```bash
docker compose down -v
```

> **Warning:** `down -v` removes Docker volumes containing PostgreSQL and other application data.

Do not use this command if you want to preserve your data.

---

# Updating FreeSelfTrack

Before updating, take a coordinated PostgreSQL and MinIO backup. If attachments still live
in PostgreSQL (before TASK-024), first follow the
[cutover procedure](docs/development/attachments.md#existing-installations-explicit-cutover).
Normal startup with `alembic upgrade head` does not transfer legacy files automatically.

To update to the latest version:

```bash
cd /opt/freeselftrack
```

Pull the latest changes:

```bash
git pull
```

Rebuild and restart the containers:

```bash
docker compose up -d --build
```

Check the status:

```bash
docker compose ps
```

When the backend starts, it automatically applies database migrations:

```text
alembic upgrade head
```

Therefore, database migrations are applied automatically when updating the application.

---

# Viewing Logs

View logs from all services:

```bash
docker compose logs
```

Follow logs in real time:

```bash
docker compose logs -f
```

Backend logs:

```bash
docker compose logs -f backend
```

Frontend logs:

```bash
docker compose logs -f frontend
```

Deadline worker logs:

```bash
docker compose logs -f deadline-worker
```

Registration mail worker logs:

```bash
docker compose logs -f registration-mail-worker
```

Attachment scanning and cleanup:

```bash
docker compose logs -f clamav attachment-scan-worker attachment-cleanup-worker
```

View the last 100 lines from the backend:

```bash
docker compose logs --tail=100 backend
```

---

# Health Checks

The backend provides a health endpoint:

```text
/api/health
```

There is also an internal health endpoint:

```text
/health
```

You can check the backend from inside its container:

```bash
docker compose exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

The expected response is:

```text
{"status":"ok"}
```

The frontend also provides:

```text
/health
```

Check it with:

```bash
curl http://localhost:5173/health
```

Expected response:

```text
ok
```

---

# Using Your Own Domain

For remote server access, put an HTTPS reverse proxy in front of FreeSelfTrack. Keep port `5173` bound to loopback; Secure session cookies require HTTPS for remote access.

For example:

```text
https://tasks.example.com
            │
            ▼
       Reverse Proxy
            │
            ▼
    FreeSelfTrack :5173
```

You can use:

* Nginx;
* Caddy;
* Traefik.

A reverse proxy allows you to use:

* HTTPS;
* your own domain;
* automatic TLS certificates;
* the standard HTTPS port `443`.

For initial local testing, use http://localhost:5173. Configure DNS and an HTTPS reverse proxy
before accessing the application remotely; Secure session cookies require HTTPS.

---

# Example Nginx Configuration

For `tasks.example.com`, set the following in `.env`:

```env
PUBLIC_APP_URL=https://tasks.example.com
PUBLIC_HOST=tasks.example.com
FRONTEND_BIND_ADDRESS=127.0.0.1
FRONTEND_PORT=5173
```

Use the [provided nginx TLS example](deploy/nginx-tls.conf.example). It is intended for
nginx running on the same host as Docker Compose:

1. Configure domain DNS and obtain a trusted TLS certificate with automatic renewal.
2. Replace `tracker.example.com` with your domain and set the certificate and private-key
   paths. Include the file in the host nginx `http` context; reconcile its `default_server`
   declarations with existing virtual hosts.
3. Run `sudo nginx -t`, then `sudo systemctl reload nginx` for nginx managed by systemd.
4. Apply application settings with `docker compose up -d --build`.
5. Open `https://tasks.example.com` and verify sign-in, session refresh and attachment downloads.

The example redirects HTTP to a fixed HTTPS hostname with status 308, rejects unknown hosts,
and adds HSTS only to HTTPS responses. TLS terminates at host nginx, which forwards requests
to `http://127.0.0.1:5173`. Expose only the reverse proxy's ports 80/443 externally; keep the
internal frontend and backend ports private.

If the reverse proxy runs in another container or on another machine, configure upstream
connectivity separately: `127.0.0.1` inside a container refers to that container itself.
For initial local testing, use `http://localhost:5173`.

---

# Security

If FreeSelfTrack is accessible from the Internet, we recommend:

1. use a strong PostgreSQL password;
2. generate a random `AUTH_SECRET_KEY`;
3. do not expose PostgreSQL directly to the Internet;
4. do not expose Redis directly to the Internet;
5. use HTTPS;
6. create regular backups;
7. keep Docker images and FreeSelfTrack updated;
8. configure a firewall on the server.

In the standard configuration, PostgreSQL is bound to:

```text
127.0.0.1
```

so it should not be directly accessible from the Internet.

Redis is also not exposed externally.

Browser protection is enabled in the backend and production nginx:

* CORS permits explicit origins, methods and headers only; wildcard or malformed origins
  prevent startup. Compose derives allowed origins from `PUBLIC_APP_URL`.
* CSP blocks inline scripts and framing. Responses also include `nosniff`, `Referrer-Policy`,
  `Permissions-Policy` and `X-Frame-Options`; attachment protections are preserved.
  Inline styles remain allowed for dynamic interface dimensions.
* Login, refresh and logout require an exact Origin and `X-CSRF-Protection: 1`.
  Other protected API operations use bearer tokens; cookies alone do not grant access.
* Uvicorn runs with `--no-proxy-headers`. Trusted proxies for authentication IP limits are
  configured explicitly through `TRUSTED_PROXY_NETWORKS`, a JSON list of IPs/CIDRs.
  The default empty list means users behind a proxy share its IP limit. The TLS example
  preserves this behavior; forwarding original client IPs through multiple proxies requires
  separate trusted-peer configuration. Never trust arbitrary forwarded headers.

---

# Backups

Metadata lives in PostgreSQL; attachment bytes live in `minio_data`. A SQL dump does not
contain attachments. Back up and restore both stores from the same checkpoint. Before backup,
stop the backend and all workers using the command below, then save the database dump and a
snapshot/copy of `minio_data`. Resume only after both operations finish. See the
[recovery instructions](docs/development/attachments.md#cleanup-and-recovery).

Find the database container:

```bash
docker compose ps
```

Before backup or restore, stop application writes:

```bash
docker compose stop backend deadline-worker registration-mail-worker attachment-scan-worker attachment-cleanup-worker
```

Create a SQL backup:

```bash
docker compose exec -T db \
  pg_dump -U tracker tracker > freeselftrack-backup.sql
```

To restore the database:

```bash
cat freeselftrack-backup.sql | \
  docker compose exec -T db \
  psql -U tracker tracker
```

Restore PostgreSQL and MinIO from the coordinated backup, then start the services:

```bash
docker compose start backend deadline-worker registration-mail-worker attachment-scan-worker attachment-cleanup-worker
```

---

# Changing the Port

By default, the frontend is available on:

```text
5173
```

If port `5173` is already in use, change:

```env
FRONTEND_PORT=8080
PUBLIC_APP_URL=https://tasks.example.com
```

Keep the HTTPS address in `PUBLIC_APP_URL` and update the reverse proxy upstream to the new frontend port. For local testing use `http://localhost:8080`.

Then restart the application:

```bash
docker compose up -d
```

FreeSelfTrack will then be available at:

```text
https://tasks.example.com
```

---

# Local Development

If you want to develop FreeSelfTrack rather than simply deploy it, you can run the frontend and backend separately.

## Backend

The backend requires:

* Python 3.13+;
* PostgreSQL;
* Redis;
* MinIO and ClamAV with the attachment scan worker for file uploads;
* ADMIN_EMAIL and ADMIN_PASSWORD for administrator bootstrap.

The project uses `uv` for Python dependency management.

Install dependencies:

```bash
cd backend
uv sync
```

Start the backend:

```bash
uv run uvicorn app.main:app --reload --no-proxy-headers
```

The backend will be available at:

```text
http://localhost:8000
```

OpenAPI schema:

```text
http://localhost:8000/openapi.json
```

Interactive `/docs` and `/redoc` are disabled under the restrictive CSP.

### Sending Email in Local Development

For direct Python processes, use environment variables prefixed with `TRACKER_`: `TRACKER_SMTP_HOST`, `TRACKER_SMTP_PORT`, `TRACKER_SMTP_SECURITY`, `TRACKER_SMTP_USERNAME`, `TRACKER_SMTP_PASSWORD`, `TRACKER_SMTP_SENDER`, and `TRACKER_PUBLIC_APP_URL`. You can also set them in `backend/.env`; the root `.env` is used by Docker Compose.

In a separate terminal, from `backend/`, run:

```bash
uv run python -m app.workers.registration_mail
```

The API and worker must share `TRACKER_DATABASE_URL` and `TRACKER_AUTH_SECRET_KEY`. For the default Vite setup, use `TRACKER_PUBLIC_APP_URL=http://localhost:5173`.

### Attachments in Local Development

Configure MinIO, ClamAV and `TRACKER_S3_*` / `TRACKER_CLAMD_*` settings using the
[operations guide](docs/development/attachments.md). In separate terminals from `backend/`, run:

```bash
uv run python -m app.workers.attachment_scan
```

```bash
uv run python -m app.workers.attachment_cleanup
```

## Frontend

The frontend requires Node.js.

Install dependencies:

```bash
cd frontend
npm ci
```

Start the development server:

```bash
npm run dev
```

Vite will display the local frontend address in the terminal. Vite is for local development; nginx applies the production browser security policies. Do not expose Vite publicly.

---

# Technology Stack

## Backend

* Python 3.13;
* FastAPI;
* SQLAlchemy;
* Alembic;
* PostgreSQL;
* Redis;
* Pydantic;
* JWT;
* Uvicorn.

## Frontend

* React;
* TypeScript;
* Vite;
* React Router;
* TanStack Query;
* nginx.

## Deployment

* Docker;
* Docker Compose.

---

# Project Structure

The main directories are:

```text
FreeSelfTrack/
│
├── backend/
│   ├── app/
│   ├── alembic/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── package-lock.json
│
├── deploy/
│   └── nginx-tls.conf.example
│
├── docker-compose.yml
├── .env.example
├── whitepaper.md
├── LICENSE
└── NOTICE
```

---

# API

The backend provides a REST API.

Interactive Swagger (`/docs`) and ReDoc (`/redoc`) are disabled. When running the backend directly for local development, its OpenAPI schema is available at:

```text
http://localhost:8000/openapi.json
```

In a production deployment, the backend is not intended to be exposed directly to the Internet. Requests to `/api/*` are normally proxied through the frontend nginx container.

---

# Current Limitations

FreeSelfTrack is under active development.

Some features may be incomplete or change between versions.

Before using FreeSelfTrack for critical production workloads, we recommend:

* testing database backup and restoration;
* configuring HTTPS;
* verifying user access controls;
* setting up monitoring;
* defining an update procedure;
* creating regular backups.

---

# Troubleshooting

## Attachments unavailable or scanning takes too long

```bash
docker compose ps minio clamav attachment-scan-worker
docker compose logs --tail=100 attachment-scan-worker clamav attachment-cleanup-worker
```

For `pending` files, check ClamAV readiness, signature updates and worker access to MinIO/DB.
Do not bypass scanning by manually setting `ready`. If an older UI shows
`Attachment unavailable` for HTTP 429, rebuild the frontend and reload:

```bash
docker compose up -d --no-deps --build frontend
```

Press Ctrl+Shift+R. The current client queues downloads and retries temporary limits.
For other errors, inspect backend logs and the user's access to the task.


## Account creation or password recovery

No confirmation or reset email is sent. Ask a system administrator for a new temporary password.
Organization managers can create users in their organizations but cannot reset passwords.
Old verification/reset links are disabled even when their original expiration has not passed.

---

## Containers are not starting

Check the container status:

```bash
docker compose ps
```

Then inspect the logs:

```bash
docker compose logs --tail=200
```

---

## Backend is not starting

Check the backend logs:

```bash
docker compose logs --tail=200 backend
```

Common causes include:

* incorrect PostgreSQL password;
* incorrect `TRACKER_DATABASE_URL`;
* a damaged Docker volume;
* a database migration error.

---

## Frontend is not accessible

Check:

```bash
docker compose ps
```

Then:

```bash
docker compose logs --tail=200 frontend
```

Check whether the port is listening:

```bash
ss -lntp | grep 5173
```

On a server, check DNS, the TLS reverse proxy and access to its ports 80/443.
Port `5173` is local-only by default; it does not need to be exposed externally.
If nginx closes the connection or the backend returns `400 Invalid host header`, check
`PUBLIC_HOST`, `PUBLIC_APP_URL` and the Host header sent by the proxy.

## Login or Session Restoration Returns 403

Open the exact address in `PUBLIC_APP_URL`: `localhost` and `127.0.0.1` are different
origins, as are different schemes or ports. After changing `.env`, run `docker compose up -d`.
Custom clients must supply Origin and `X-CSRF-Protection: 1` for login, refresh and logout;
keep CSRF checks enabled. If backend startup rejects a CORS/URL setting, remove wildcards,
paths and trailing `/` from the origin. Remote access requires HTTPS; local Secure-cookie
support on localhost depends on the browser.

---

## PostgreSQL is not starting

Check:

```bash
docker compose logs --tail=200 db
```

Check the database container status:

```bash
docker compose ps db
```

---

## The application stopped working after an update

Start by checking the backend logs:

```bash
docker compose logs --tail=200 backend
```

If the problem is related to database migrations, **do not immediately delete the PostgreSQL volume**.

Deleting the volume may permanently remove all application data.

Create a database backup before attempting destructive troubleshooting.

---

# Removing FreeSelfTrack

To remove the application containers:

```bash
docker compose down
```

To remove the application containers and all stored Docker volumes:

```bash
docker compose down -v
```

Before using the second command, make sure you no longer need the stored data or have a valid backup.

---

# Development

If you would like to contribute to FreeSelfTrack:

1. create a fork of the repository;
2. create a separate branch;
3. make your changes;
4. add tests for new functionality;
5. verify the backend and frontend;
6. open a Pull Request.

Source code:

**https://github.com/Badmajor/FreeSelfTrack**

---

# License

FreeSelfTrack is licensed under the **FreeSelfTrack Attribution License 1.0 (FSTAL-1.0)**.

You are free to:

* use FreeSelfTrack;
* use it for commercial purposes;
* self-host it;
* modify the source code;
* create derivative works;
* distribute original or modified versions;
* provide paid hosting;
* provide installation services;
* provide support and customization services.

When distributing FreeSelfTrack or a derivative work, the original attribution must be retained:

> **FreeSelfTrack by Viktor Balonkin**
> https://github.com/Badmajor/FreeSelfTrack

For the complete license terms, see:

* [`LICENSE`](LICENSE)
* [`NOTICE`](NOTICE)

Third-party libraries, frameworks, Docker images, and other external components are distributed under their respective licenses.

---

# Author

**Viktor Balonkin**

Original project:

https://github.com/Badmajor/FreeSelfTrack

---

# Feedback

If you find a bug or have an idea for an improvement, please create an Issue in the repository:

https://github.com/Badmajor/FreeSelfTrack/issues


## Sessions and account security

TASK-022 requires migration `0014_auth_sessions` and a coordinated backend/frontend/mail-worker
upgrade. Existing JWTs are rejected; sign in again. Access tokens live only in memory and refresh
credentials use Secure HttpOnly SameSite cookies. Logout immediately revokes the current session.
AUTH_SECRET_KEY has no fallback and must be generated randomly (`openssl rand -hex 32`).
Shared deployments require HTTPS and the exact PUBLIC_APP_URL for cookie, CORS and CSRF behavior.
Plain HTTP access by server IP cannot retain Secure refresh cookies.

Profile offers password change with the current password for ordinary users. Self-deactivation
is disabled. Configuration administrator credentials are controlled by ADMIN_*. Password change
and administrative reset end all affected sessions. Public registration, email recovery and old
confirmation/reset links are disabled. Contact an administrator for a new temporary password.

## Configuration administrator and roles (TASK-031)

Set nonempty `ADMIN_EMAIL` and `ADMIN_PASSWORD` in your local environment or `.env` before
starting Compose/API. These names have **no TRACKER_ prefix**. Do not commit credentials.
No email-format or password-complexity policy applies to this account; login accepts its
configured identifier and password. Ordinary permanent-password policy remains unchanged.

After migrations, API startup runs bootstrap before serving health/API requests. It creates or
reuses the normalized (`strip().casefold()`) identifier, unblocks it, clears the temporary-password
flag and applies the configured Argon2 password. Restarting with unchanged credentials preserves
sessions. Changing credentials or the system role revokes affected sessions and pending email
actions. Changing ADMIN_EMAIL selects another account, preserving both accounts' memberships and
local roles; it does not rename the old account or reactivate revoked memberships.
All replicas must receive identical configuration. Administrator credentials can only be changed
by updating ADMIN_* and restarting; profile password changes, email reset and self-deactivation
cannot alter this account. Self-deactivation is disabled for everyone.

Migrations `0020_administration_roles` and `0021_remove_ownership` replace owner_id with
member/manager roles and active/archived/revoked membership states. Inactive users and archived
scopes do not acquire active grants. Zero or multiple managers are valid; creating organizations
(SA only) or projects (SA/scoped OM) does not add the creator. Workflow changes require SA, scoped
OM or scoped PM. Transfer-ownership endpoints are removed; clients use backend capabilities.
Downgrade cannot reconstruct ownership; use a coordinated pre-transition backup if needed.

This is an intermediate development stage. Membership UI, complete read matrix, archive
lifecycle and audit views remain TASK-033–037. User lifecycle is implemented; registration
and email recovery are disabled by TASK-032. Do not deploy this intermediate stage over a shared existing
installation: follow the [coordinated migration plan](docs/architecture/administration-migration.md).


## Administrative user lifecycle (TASK-032)

Open **Users** in the sidebar. The system administrator creates users without membership or
in an organization; an organization manager selects an organization they manage. Creation and
initial membership commit together. The temporary password is displayed once, is not emailed,
and is stored only as an Argon2 hash. Share it securely; after closing the result, only the
system administrator can issue a replacement. It has no expiry and permits repeated sign-in,
but only password change, session refresh and logout are available until a permanent password
is set. Changing it signs out every session; sign in again with the permanent password.

System administrators and active organization managers can block/unblock users globally,
including equal-level managers. Blocking revokes every session and all memberships/manager
roles. Unblocking restores neither memberships nor roles. Task participant IDs remain unchanged;
a blocked assignee is shown struck through with a readable label. The configuration administrator
cannot be blocked or have their password reset through the API/UI.

Migration `0022_disable_public_auth` invalidates old registration/reset outboxes, preserving
existing users, passwords and audit records. Deploy API, SPA and cleanup worker together with
writers stopped; use the [release plan](docs/architecture/administration-migration.md).
New user mutations and the paginated user directory are implemented; full user cards, profile/email
administration, membership administration and audit views remain in later tasks.
