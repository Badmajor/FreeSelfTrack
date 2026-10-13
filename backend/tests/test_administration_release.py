"""TASK-038: isolated clean/legacy Compose release rehearsal, no shared resources."""

import asyncio
import hashlib
import io
import json
import os
import secrets
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient
from legacy_audit_helpers import seed_legacy_audit
from minio import Minio
from release_browser_helpers import check_release_ui
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ADMINISTRATION_RELEASE") != "1", reason="Opt-in disposable full release"
)
PASSWORD = "release permanent password 038"


@pytest.fixture(params=["clean", "legacy"])
def release_stack(request, tmp_path):
    name = "fst038-" + uuid4().hex[:10]
    override = tmp_path / "compose.yml"
    override.write_text("""services:
  minio:
    ports: ['127.0.0.1::9000']
  smtp:
    image: mailhog/mailhog:v1.0.1
    networks: [app]
    ports: ['127.0.0.1::8025']
""")
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        frontend_port = str(port_socket.getsockname()[1])
    origin = "http://localhost:" + frontend_port
    env = {
        **os.environ,
        "POSTGRES_USER": "migration",
        "POSTGRES_PASSWORD": "disposable-migration",
        "POSTGRES_DB": "tracker",
        "POSTGRES_PORT": "0",
        "FRONTEND_PORT": frontend_port,
        "ADMIN_EMAIL": "release-admin",
        "ADMIN_PASSWORD": "x",
        "AUTH_SECRET_KEY": secrets.token_hex(32),
        "MINIO_ROOT_USER": "testadmin",
        "MINIO_ROOT_PASSWORD": "disposable-storage",
        "S3_BUCKET": "tracker-attachments",
        "PUBLIC_HOST": "localhost",
        "PUBLIC_APP_URL": origin,
        "SMTP_HOST": "smtp",
        "SMTP_PORT": "1025",
        "SMTP_SECURITY": "plain",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "SMTP_SENDER": "release@example.com",
        "TRACKER_DATABASE_URL": "postgresql+asyncpg://runtime:disposable-runtime@db:5432/tracker",
    }
    base = [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "-p",
        name,
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(ROOT / "deploy/compose.runtime.yml"),
        "-f",
        str(override),
    ]

    def compose(*args, input=None):
        result = subprocess.run(
            [*base, *args], env=env, input=input, capture_output=True, text=True, timeout=600
        )
        assert result.returncode == 0, result.stderr[-6000:]
        return result.stdout

    def sql(statement):
        return compose(
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "migration",
            "-d",
            "tracker",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            input=statement,
        )

    def migrate(revision):
        compose(
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "TRACKER_DATABASE_URL=postgresql+asyncpg://migration:disposable-migration@db:5432/tracker",
            "backend",
            "alembic",
            "upgrade",
            revision,
        )

    try:
        compose("config", "--quiet")
        compose(
            "build",
            "backend",
            "frontend",
            "registration-mail-worker",
            "deadline-worker",
            "attachment-cleanup-worker",
            "attachment-scan-worker",
        )
        compose("up", "-d", "--wait", "--wait-timeout", "120", "db", "redis", "minio", "smtp")
        port = compose("port", "db", "5432").strip()
        storage = Minio(
            compose("port", "minio", "9000").strip(),
            access_key="testadmin",
            secret_key="disposable-storage",
            secure=False,
        )
        yield {
            "compose": compose,
            "sql": sql,
            "migrate": migrate,
            "storage": storage,
            "url": f"postgresql+asyncpg://migration:disposable-migration@{port}/tracker",
            "origin": origin,
            "secret": env["AUTH_SECRET_KEY"],
            "mode": request.param,
            "directory": tmp_path,
        }
    finally:
        compose("down", "-v", "--remove-orphans")


async def legacy_checkpoint(stack, engine):
    """Back up and restore synthetic 0018 SQL and object bytes before the upgrade."""
    stack["migrate"]("0018_audit_integrity")
    payload = b"preserved legacy release attachment"
    key = "attachments/" + uuid4().hex
    stack["storage"].put_object("tracker-attachments", key, io.BytesIO(payload), len(payload))
    async with engine.begin() as connection:
        ids = await seed_legacy_audit(connection)
        ids.update(
            comment=uuid4(),
            attachment=uuid4(),
            session=uuid4(),
            key=key,
            digest=hashlib.sha256(payload).hexdigest(),
            size=len(payload),
        )
        for statement in (
            "DELETE FROM project_members",  # Known owner must be backfilled, not lost.
            "UPDATE organizations SET deleted_at='2020-01-02T03:04:05Z'",
            "UPDATE tasks SET assignee_id=:user",
            "INSERT INTO notifications(id,recipient_id,task_id,event_type,message,created_at) "
            "VALUES (gen_random_uuid(),:user,:task,'task_created','Legacy notification',now())",
            "INSERT INTO comments(id,task_id,author_id,request_id,fingerprint,"
            "sequence,text,created_at) "
            "VALUES (:comment,:task,:user,:request,:digest,1,'Legacy chat',now())",
            "INSERT INTO attachments(id,comment_id,filename,media_type,size,"
            "position,object_key,sha256,state) "
            "VALUES (:attachment,:comment,'legacy.txt','text/plain',:size,0,:key,:digest,'ready')",
            "INSERT INTO auth_sessions(id,user_id,created_at,expires_at) "
            "VALUES (:session,:user,now(),now()+interval '1 day')",
        ):
            await connection.execute(text(statement), ids)
        ids["refresh"] = secrets.token_urlsafe(32)
        await connection.execute(
            text("INSERT INTO refresh_credentials(token_hash,session_id) VALUES (:hash,:session)"),
            {
                "hash": hashlib.sha256(ids["refresh"].encode()).hexdigest(),
                "session": ids["session"],
            },
        )
        snapshots = {}
        for table in (
            "tasks",
            "notifications",
            "task_history",
            "security_events",
            "comments",
            "attachments",
            "task_links",
            "project_statuses",
        ):
            snapshots[table] = list(
                await connection.scalars(
                    text(f"SELECT (to_jsonb(t) - 'archived_at')::text FROM {table} t ORDER BY id")
                )
            )
    # Restore to a different database and bucket; never overwrite a live installation.
    compose = stack["compose"]
    compose(
        "exec",
        "-T",
        "db",
        "pg_dump",
        "-U",
        "migration",
        "-Fc",
        "-f",
        "/tmp/release.dump",
        "tracker",
    )
    compose("exec", "-T", "db", "createdb", "-U", "migration", "restored")
    compose(
        "exec",
        "-T",
        "db",
        "pg_restore",
        "-U",
        "migration",
        "--exit-on-error",
        "-d",
        "restored",
        "/tmp/release.dump",
    )
    restored = create_async_engine(stack["url"].rsplit("/", 1)[0] + "/restored")
    try:
        async with restored.connect() as connection:
            for table, expected in snapshots.items():
                assert (
                    list(
                        await connection.scalars(
                            text(
                                "SELECT (to_jsonb(t) - 'archived_at')::text "
                                f"FROM {table} t ORDER BY id"
                            )
                        )
                    )
                    == expected
                )
    finally:
        await restored.dispose()
    storage = stack["storage"]
    storage.make_bucket("restored-attachments")
    response = storage.get_object("tracker-attachments", key)
    try:
        backup = response.read()
    finally:
        response.close()
        response.release_conn()
    storage.put_object("restored-attachments", key, io.BytesIO(backup), len(backup))
    response = storage.get_object("restored-attachments", key)
    try:
        assert hashlib.sha256(response.read()).hexdigest() == ids["digest"]
    finally:
        response.close()
        response.release_conn()
    now = datetime.now(UTC)
    ids["access"] = jwt.encode(
        {
            "sub": str(ids["user"]),
            "sid": str(ids["session"]),
            "jti": str(uuid4()),
            "iss": "freeselftrack",
            "aud": "freeselftrack-api",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        stack["secret"],
        algorithm="HS256",
    )
    return ids, snapshots


async def test_release_rehearsal(release_stack):
    stack = release_stack
    compose, sql = stack["compose"], stack["sql"]
    engine = create_async_engine(stack["url"])
    try:
        legacy = await legacy_checkpoint(stack, engine) if stack["mode"] == "legacy" else None
        stack["migrate"]("head")
        if legacy:
            ids, snapshots = legacy
            async with engine.connect() as connection:
                for table, expected in snapshots.items():
                    assert (
                        list(
                            await connection.scalars(
                                text(
                                    "SELECT (to_jsonb(t) - 'archived_at')::text "
                                    f"FROM {table} t ORDER BY id"
                                )
                            )
                        )
                        == expected
                    )
                assert (
                    await connection.scalar(text("SELECT state FROM project_members")) == "archived"
                )
                assert (
                    await connection.scalar(text("SELECT role FROM project_members")) == "manager"
                )
                assert (
                    await connection.scalar(
                        text("SELECT count(*) FROM tasks WHERE archived_at IS NOT NULL")
                    )
                    == 2
                )
            # Maintenance SQL: writers stopped, one technical event per session.
            sql((ROOT / "deploy/administration-cutover.sql").read_text())
            assert (
                sql("SELECT count(*) FROM auth_sessions WHERE revoked_at IS NULL;").strip() == "0"
            )
            assert (
                sql(
                    "SELECT count(*) FROM security_events WHERE event_type='session_revoked';"
                ).strip()
                == "1"
            )
            sql((ROOT / "deploy/administration-cutover.sql").read_text())
            assert (
                sql(
                    "SELECT count(*) FROM security_events WHERE event_type='session_revoked';"
                ).strip()
                == "1"
            )
        sql("""CREATE ROLE runtime LOGIN PASSWORD 'disposable-runtime'
NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE tracker TO runtime;
GRANT USAGE ON SCHEMA public TO runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO runtime;
""")
        compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
            "backend",
            "frontend",
            "registration-mail-worker",
            "deadline-worker",
            "attachment-cleanup-worker",
        )
        origin = stack["origin"]
        async with AsyncClient(
            base_url=origin,
            timeout=30,
            headers={"Origin": origin, "X-CSRF-Protection": "1"},
        ) as http:

            async def call(method, path, token=None, expected=200, **kwargs):
                headers = {"Authorization": "Bearer " + token} if token else {}
                response = await http.request(method, "/api" + path, headers=headers, **kwargs)
                assert response.status_code == expected, (
                    method,
                    path,
                    response.status_code,
                    response.text,
                )
                return response.json() if response.content else None

            async def login(email, password):
                return (
                    await call("POST", "/auth/login", json={"email": email, "password": password})
                )["access_token"]

            if legacy:
                await call("GET", "/users", ids["access"], 401)
                old_refresh = await http.post(
                    "/api/auth/refresh",
                    headers={
                        "Cookie": "__Secure-fst-refresh=" + ids["refresh"],
                    },
                )
                assert old_refresh.status_code == 401
            admin = await login("release-admin", "x")
            org = (
                await call(
                    "POST", "/organizations", admin, 201, json={"name": "Release organization"}
                )
            )["id"]

            async def account(label, creator, path="/users"):
                email = label + "@example.com"
                created = await call(
                    "POST",
                    path,
                    creator,
                    201,
                    json={"email": email, "first_name": label, "last_name": "Release"},
                )
                temporary = created["temporary_password"]
                first = await login(email, temporary)
                await call("GET", "/users", first, 403)
                second = await login(email, temporary)
                await call(
                    "POST",
                    "/auth/password/change",
                    second,
                    204,
                    json={"current_password": temporary, "new_password": PASSWORD},
                )
                await call("GET", "/users", first, 401)
                return created["user"]["id"], await login(email, PASSWORD)

            manager_id, manager = await account("manager", admin)
            await call(
                "PUT", f"/organizations/{org}/members/{manager_id}", admin, json={"role": "manager"}
            )
            user_id, user = await account("employee", manager, f"/organizations/{org}/users")
            pm_id, pm = await account("project-manager", manager, f"/organizations/{org}/users")
            project = (
                await call(
                    "POST",
                    "/projects",
                    manager,
                    201,
                    json={
                        "organization_id": org,
                        "name": "Release project",
                        "manager_ids": [pm_id],
                    },
                )
            )["id"]
            await call("PUT", f"/projects/{project}/members/{user_id}", pm, json={"role": "member"})
            statuses = await call("GET", f"/projects/{project}/statuses", user)
            task = await call(
                "POST",
                f"/projects/{project}/tasks",
                user,
                201,
                json={
                    "title": "Release task",
                    "status_id": statuses[0]["id"],
                    "assignee_id": user_id,
                },
            )
            task_id = task["id"]
            comment = await call(
                "POST",
                f"/tasks/{task_id}/comments",
                user,
                201,
                data={
                    "metadata": json.dumps(
                        {"request_id": str(uuid4()), "text": "Release chat", "mention_ids": []}
                    )
                },
                files=[("files", ("release.txt", b"release clean attachment", "text/plain"))],
            )
            attachment = comment["attachments"][0]["id"]
            compose(
                "up", "-d", "--wait", "--wait-timeout", "420", "clamav", "attachment-scan-worker"
            )
            for _ in range(120):
                current = await call("GET", f"/tasks/{task_id}/comments/{comment['id']}", user)
                if current["attachments"][0]["state"] != "pending":
                    break
                await asyncio.sleep(1)
            assert current["attachments"][0]["state"] == "ready"
            content_path = f"/api/attachments/{attachment}/content"
            assert (
                await http.get(content_path, headers={"Authorization": "Bearer " + user})
            ).content == b"release clean attachment"
            await call(
                "POST", "/users/me/email-change", user, 202, json={"email": "changed@example.com"}
            )
            mail_url = "http://" + compose("port", "smtp", "8025").strip()
            for _ in range(60):
                mail = (await http.get(mail_url + "/api/v2/messages")).json()
                if mail["total"]:
                    break
                await asyncio.sleep(1)
            assert mail["total"] == 1
            assert "email-change=" in mail["items"][0]["Content"]["Body"]
            await call("POST", f"/users/{user_id}/block", manager, json={"confirm": True})
            await call("GET", f"/tasks/{task_id}", user, 401)
            await call("POST", "/auth/refresh", expected=401)
            await call("POST", f"/users/{user_id}/unblock", manager)
            user = await login("employee@example.com", PASSWORD)
            await call("GET", f"/tasks/{task_id}", user, 404)
            retained = await call("GET", f"/tasks/{task_id}", admin)
            assert all(
                retained[key] == task[key] for key in ("created_by", "reporter_id", "assignee_id")
            )
            for scope in (f"organizations/{org}", f"projects/{project}"):
                await call("PUT", f"/{scope}/members/{user_id}", admin, json={"role": "member"})
            await call("DELETE", f"/projects/{project}/members/{user_id}", pm, 204)
            await call("GET", f"/tasks/{task_id}", user, 404)
            await call("PUT", f"/projects/{project}/members/{user_id}", pm, json={"role": "member"})
            await call("POST", f"/organizations/{org}/archive", admin, json={"confirm": True})
            assert (await call("GET", f"/tasks/{task_id}", user))["archived_at"]
            await call("PATCH", f"/tasks/{task_id}", admin, 409, json={"title": "Forbidden"})
            await call("POST", f"/tasks/{task_id}/restore", admin, 409)
            assert (
                await http.get(content_path, headers={"Authorization": "Bearer " + user})
            ).status_code == 200
            await call("POST", f"/organizations/{org}/restore", admin)
            await call("GET", f"/tasks/{task_id}", user, 404)
            await call("POST", f"/projects/{project}/restore", admin)
            await call("POST", f"/tasks/{task_id}/restore", admin)
            for scope in (f"organizations/{org}", f"projects/{project}"):
                await call("PUT", f"/{scope}/members/{user_id}", admin, json={"role": "member"})
            assert (await call("GET", f"/tasks/{task_id}", user))["assignee"][
                "unavailable_reasons"
            ] == []
            audit = await call("GET", f"/tasks/{task_id}/audit", user)
            assert audit["page_size"] == 20
            assert [event["action"] for event in audit["items"]] == ["restored", "archived"]
            await call("GET", f"/users/{manager_id}/audit", user, 403)
            for route in (
                "register",
                "verify-email",
                "password/reset-request",
                "password/reset",
                "deactivate",
            ):
                await call("POST", "/auth/" + route, user, 404, json={"token": "old-link"})
            if legacy:
                assert (
                    await http.get(
                        f"/api/attachments/{ids['attachment']}/content",
                        headers={"Authorization": "Bearer " + admin},
                    )
                ).content == b"preserved legacy release attachment"
            if stack["mode"] == "clean":
                browser_user = await call(
                    "POST",
                    "/users",
                    admin,
                    201,
                    json={
                        "email": "browser-user@example.com",
                        "first_name": "Browser",
                        "last_name": "User",
                    },
                )
                for index in range(21):
                    await call(
                        "PATCH",
                        f"/organizations/{org}",
                        admin,
                        json={"description": f"Browser pagination {index}"},
                    )
                await asyncio.to_thread(
                    check_release_ui,
                    origin,
                    stack["directory"],
                    browser_user["temporary_password"],
                    PASSWORD,
                    org,
                )
        # The real runtime cannot own/alter tables, bypass triggers or migrate.
        runtime = create_async_engine(
            stack["url"].replace("migration:disposable-migration", "runtime:disposable-runtime")
        )
        try:
            from sqlalchemy.exc import DBAPIError

            for statement in (
                "CREATE TABLE forbidden(id int)",
                "ALTER TABLE task_history DISABLE TRIGGER ALL",
                "UPDATE administrative_audit_events SET action=action",
                "DELETE FROM security_events",
                "TRUNCATE task_history",
            ):
                async with runtime.begin() as connection:
                    with pytest.raises(DBAPIError):
                        await connection.execute(text(statement))
        finally:
            await runtime.dispose()
    finally:
        await engine.dispose()
