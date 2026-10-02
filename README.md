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

* user registration with SMTP email confirmation and authentication;
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
* file attachments;
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

To run the containers, you need Docker with Docker Compose support. New user registration also requires an accessible SMTP server, either your own or your email provider's.

## 1. Requirements

At minimum, you need:

* a Linux server;
* Docker;
* Docker Compose;
* SSH access to the server;
* an available TCP port for the web interface;
* an SMTP server and connection settings for confirmation emails.

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

At minimum, change the database password and application secret, configure SMTP, and set the public application address in `PUBLIC_APP_URL`.

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

FRONTEND_BIND_ADDRESS=0.0.0.0
FRONTEND_PORT=5173

PUBLIC_APP_URL=http://localhost:5173
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=YOUR_SMTP_USERNAME
SMTP_PASSWORD=YOUR_SMTP_PASSWORD
SMTP_SENDER=noreply@example.com
```

## Connect an SMTP Server

New accounts are created only after email confirmation. Registration cannot be completed without working SMTP; existing users can still sign in. Compose does not include a mail server: configure your own server or your email provider's settings.

| Variable | Value |
| --- | --- |
| `PUBLIC_APP_URL` | Frontend address reachable by users, such as `https://tasks.example.com`. Confirmation links use this address. Use `localhost` only for local development. |
| `SMTP_HOST` | SMTP hostname or address reachable from the container. `localhost` inside the worker refers to that container itself. |
| `SMTP_PORT` | SMTP port: usually `587` for STARTTLS or `465` for TLS. |
| `SMTP_SECURITY` | `starttls` for STARTTLS or `tls` for TLS from the start of the connection. Use `plain` only with an isolated local test mail server. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Credentials supplied by your email provider; use an app password if required. Leave both empty for a server that requires no authentication. |
| `SMTP_SENDER` | Sender email address authorized by your SMTP server. |

Replace the example values in `.env` with your settings. Both `starttls` and `tls` verify the server certificate. Do not publish `.env` containing mail credentials.

Compose automatically starts `registration-mail-worker`, which sends queued messages from PostgreSQL and retries failed deliveries. After changing `.env`, apply the settings with `docker compose up -d`. If a link does not open your application, check `PUBLIC_APP_URL` and request a new email by submitting registration again.

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

By default, the web interface is available on port `5173`.

If FreeSelfTrack is running on your local computer:

```text
http://localhost:5173
```

If it is installed on a server:

```text
https://tasks.example.com
```

Configure an HTTPS reverse proxy for the server and set PUBLIC_APP_URL to that exact public URL.
The bundled frontend listens on HTTP internally; do not use remote plain HTTP for login.

---

# 7. First Login

Open FreeSelfTrack in your browser.

1. Submit the registration form with an email address you can access and a password of at least 12 characters.
2. Open the confirmation email and follow its link.
3. Enter the password you chose during registration and confirm your email. Opening the link alone does not create an account.
4. Sign in with your email and password.

Links expire after one hour by default and can be used once. If a link expires, submit registration again. The application displays the same message for new and already registered addresses; existing accounts remain unchanged.

After confirming your email and signing in, you can create an organization:

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
                            ▼
                   ┌─────────────────┐
                   │    Frontend     │
                   │     nginx       │
                   │     :5173       │
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

The Compose configuration also contains MinIO for future object-storage use.

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

The `registration-mail-worker` container sends confirmation emails through the configured SMTP server. PostgreSQL stores the queue, request expiration and delivery state. Temporary failures are retried until the registration request expires.

---

# Data Storage

The Docker Compose configuration uses named Docker volumes.

The main volumes are:

```text
postgres_data
redis_data
minio_data
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

For a permanent Internet-facing installation, it is recommended to put a reverse proxy in front of FreeSelfTrack instead of exposing port `5173` directly.

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

Suppose your domain is:

```text
tasks.example.com
```

and FreeSelfTrack is running locally on:

```text
127.0.0.1:5173
```

Nginx can accept external requests:

```text
https://tasks.example.com
```

and forward them to FreeSelfTrack.

Example configuration:

```nginx
server {
    listen 80;
    server_name tasks.example.com;

    location / {
        proxy_pass http://127.0.0.1:5173;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

You can then use Let's Encrypt and Certbot to enable HTTPS.

When switching to your domain, update `PUBLIC_APP_URL` in `.env`, for example to `https://tasks.example.com`, and run `docker compose up -d` so new emails use the correct links.

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

---

# Backups

The main FreeSelfTrack data is stored in PostgreSQL.

Regular database backups are strongly recommended.

Find the database container:

```bash
docker compose ps
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

> Before restoring a database, it is recommended to stop the backend and both workers so that the application does not modify the database during the restore operation.

For example:

```bash
docker compose stop backend deadline-worker registration-mail-worker
```

Restore the database and then start the services:

```bash
docker compose start backend deadline-worker registration-mail-worker
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
* an SMTP server or local test mail sink for registration.

The project uses `uv` for Python dependency management.

Install dependencies:

```bash
cd backend
uv sync
```

Start the backend:

```bash
uv run uvicorn app.main:app --reload
```

The backend will be available at:

```text
http://localhost:8000
```

FastAPI documentation:

```text
http://localhost:8000/docs
```

### Sending Email in Local Development

For direct Python processes, use environment variables prefixed with `TRACKER_`: `TRACKER_SMTP_HOST`, `TRACKER_SMTP_PORT`, `TRACKER_SMTP_SECURITY`, `TRACKER_SMTP_USERNAME`, `TRACKER_SMTP_PASSWORD`, `TRACKER_SMTP_SENDER`, and `TRACKER_PUBLIC_APP_URL`. You can also set them in `backend/.env`; the root `.env` is used by Docker Compose.

In a separate terminal, from `backend/`, run:

```bash
uv run python -m app.workers.registration_mail
```

The API and worker must share `TRACKER_DATABASE_URL` and `TRACKER_AUTH_SECRET_KEY`. For the default Vite setup, use `TRACKER_PUBLIC_APP_URL=http://localhost:5173`.

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

Vite will display the local frontend address in the terminal.

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
├── docker-compose.yml
├── .env.example
├── whitepaper.md
├── LICENSE
└── NOTICE
```

---

# API

The backend provides a REST API.

When running the backend directly in development mode, FastAPI documentation is available at:

```text
http://localhost:8000/docs
```

OpenAPI schema:

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

## Confirmation Email Does Not Arrive

Check the mail worker and its logs:

```bash
docker compose ps registration-mail-worker
docker compose logs --tail=100 registration-mail-worker
```

Check the spam folder, SMTP connectivity from the container, port and encryption mode, credentials, and authorized sender address. The `confirmation_delivery_retry` event means delivery will be retried; `mail_database_unavailable` indicates that the worker cannot access PostgreSQL.

The form's “Check your email” response means the request was accepted, not that the message has already arrived. After correcting `.env`, run `docker compose up -d`. If the request's one-hour lifetime has expired, register again; frequent attempts may be temporarily rate-limited. If the email arrives but its link points to the wrong address, correct `PUBLIC_APP_URL`.

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

If the server has a firewall enabled, make sure the required port is allowed.

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

Profile offers password change and self-deactivation, both requiring the current password. Transfer
all organization/project ownership first, including restorable deleted resources. Password change,
email reset and deactivation end all sessions. “Forgot password?” uses a single-use 30-minute SMTP
link; keep registration-mail-worker running for both registration and recovery.
