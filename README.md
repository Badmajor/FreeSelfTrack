[RU](README_RU.md)

# FreeSelfTrack

**FreeSelfTrack** is a free, self-hosted task tracker for teams and small organizations.

It allows you to run your own task management system on your own server and keep your data under your own control, without requiring a mandatory dependency on a cloud SaaS provider.

> **Project status:** Early development / MVP

## Features

FreeSelfTrack is designed for managing projects, tasks, and team workflows.

Current features include:

* user registration and authentication;
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

You only need Docker with Docker Compose support.

## 1. Requirements

At minimum, you need:

* a Linux server;
* Docker;
* Docker Compose;
* SSH access to the server;
* an available TCP port for the web interface.

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

At minimum, change the database password and application secret.

Example:

```env
POSTGRES_DB=tracker
POSTGRES_USER=tracker
POSTGRES_PASSWORD=CHANGE_THIS_DATABASE_PASSWORD

POSTGRES_BIND_ADDRESS=127.0.0.1
POSTGRES_PORT=5431

TRACKER_DATABASE_URL=postgresql+asyncpg://tracker:CHANGE_THIS_DATABASE_PASSWORD@db:5432/tracker

AUTH_SECRET_KEY=CHANGE_THIS_TO_A_LONG_RANDOM_SECRET

DEADLINE_WORKER_INTERVAL_SECONDS=60

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=CHANGE_THIS_MINIO_PASSWORD

FRONTEND_BIND_ADDRESS=0.0.0.0
FRONTEND_PORT=5173
```

## Important

Do not use example passwords on a server that is accessible from the Internet.

In particular, change:

```env
POSTGRES_PASSWORD
AUTH_SECRET_KEY
MINIO_ROOT_PASSWORD
```

`AUTH_SECRET_KEY` should be a long, random value.

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
http://SERVER_IP:5173
```

For example:

```text
http://192.168.1.100:5173
```

or:

```text
http://203.0.113.10:5173
```

where `203.0.113.10` is the IP address of your server.

---

# 7. First Login

Open FreeSelfTrack in your browser.

Create a user through the registration form.

After registration, you can create an organization:

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

If you are not familiar with Nginx, HTTPS, or DNS, it is recommended to first verify that FreeSelfTrack works using:

```text
http://SERVER_IP:5173
```

and configure the domain afterwards.

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

> Before restoring a database, it is recommended to stop the backend and worker so that the application does not modify the database during the restore operation.

For example:

```bash
docker compose stop backend deadline-worker
```

Restore the database and then start the services:

```bash
docker compose start backend deadline-worker
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
```

Then restart the application:

```bash
docker compose up -d
```

FreeSelfTrack will then be available at:

```text
http://SERVER_IP:8080
```

---

# Local Development

If you want to develop FreeSelfTrack rather than simply deploy it, you can run the frontend and backend separately.

## Backend

The backend requires:

* Python 3.13+;
* PostgreSQL;
* Redis.

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
