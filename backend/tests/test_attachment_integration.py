"""Opt-in disposable Compose/MinIO/PostgreSQL checks; never touch the shared stack."""

import asyncio
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from legacy_audit_helpers import seed_legacy_audit
from minio import Minio
from minio.error import S3Error
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_chat import post

from app.core.object_storage import ObjectStorage
from app.db.session import get_session
from app.main import app
from app.repositories.chat import ChatRepository
from app.services.attachment_maintenance import AttachmentMaintenance
from app.services.errors import ConflictError
from app.services.sessions import create_access_token

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ATTACHMENT_INTEGRATION") != "1", reason="Opt-in disposable Compose integration"
)


@pytest.fixture(scope="module")
def deployment(tmp_path_factory):
    directory = tmp_path_factory.mktemp("attachment-compose")
    override = directory / "ports.yml"
    override.write_text('services:\n  minio:\n    ports: ["127.0.0.1::9000"]\n')
    env = {
        **os.environ,
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test-disposable-password",
        "POSTGRES_DB": "tracker",
        "POSTGRES_PORT": "0",
        "FRONTEND_PORT": "0",
        "PUBLIC_HOST": "localhost",
        "PUBLIC_APP_URL": "http://localhost:5173",
        "MINIO_ROOT_USER": "testadmin",
        "MINIO_ROOT_PASSWORD": "test-disposable-password",
        "S3_BUCKET": "tracker-attachments",
        "AUTH_SECRET_KEY": "79e360951e8b40b4a7029385c6fde013639cf88d5781a2e0d5f4b097ccb651a2",
        "TRACKER_DATABASE_URL": "postgresql+asyncpg://test:test-disposable-password@db:5432/tracker",
    }
    command = [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "-p",
        "fst024" + uuid4().hex[:8],
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(override),
    ]

    def compose(*args):
        return subprocess.run(
            [*command, *args], env=env, check=True, capture_output=True, text=True
        ).stdout

    try:
        config = json.loads(compose("config", "--format", "json"))
        assert (
            "minio-init" not in config["services"] and "minio-provision" not in config["services"]
        )
        minio = config["services"]["minio"]
        assert minio["environment"]["MINIO_DEFAULT_BUCKETS"] == "tracker-attachments"
        assert minio["image"].endswith(
            "@sha256:211ea94d3487bc42f9b4140f86c7d0123edba3c24160d0ef1057911504405c8e"
        )
        compose("up", "-d", "--wait", "--wait-timeout", "90", "db", "minio")
        endpoint = compose("port", "minio", "9000").strip()
        pg = compose("port", "db", "5432").strip()
        url = f"postgresql+asyncpg://test:test-disposable-password@{pg}/tracker"
        storage = ObjectStorage(
            Minio(
                endpoint,
                access_key="testadmin",
                secret_key="test-disposable-password",
                secure=False,
            ),
            "tracker-attachments",
        )
        yield compose, storage, url, endpoint
    finally:
        compose("down", "-v", "--remove-orphans")


def migrate(url, revision, action="upgrade", *, check=True):
    env = {**os.environ, "TRACKER_DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def test_native_bucket_restart_private_access_and_streaming(deployment):
    compose, storage, _, endpoint = deployment
    assert storage.client.bucket_exists(storage.bucket)
    assert storage.client.get_bucket_lifecycle(storage.bucket) is None
    key = "attachments/" + str(uuid4())

    # Multiple SDK parts; assert the source is never read unboundedly.
    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert 0 <= size <= 5 * 1024 * 1024
            return super().read(size)

    payload = b"x" * (11 * 1024 * 1024)
    storage.put(key, Bounded(payload), len(payload))
    with pytest.raises(S3Error) as denied:
        Minio(endpoint, secure=False).get_object(storage.bucket, key)
    assert denied.value.code == "AccessDenied"
    compose("restart", "minio")
    compose("up", "-d", "--wait", "--wait-timeout", "90", "minio")
    endpoint = compose("port", "minio", "9000").strip()
    storage.client = Minio(
        endpoint, access_key="testadmin", secret_key="test-disposable-password", secure=False
    )
    with io.BytesIO() as target:
        size, digest = storage.copy_to(key, target)
        assert size == len(payload) and digest == hashlib.sha256(payload).hexdigest()
    storage.delete(key)


async def test_legacy_migration_review_and_cleanup_lock(deployment, client, monkeypatch):
    _, storage, url, _ = deployment
    migrate(url, "0014_auth_sessions")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    monkeypatch.setattr("app.services.chat.get_storage", lambda: storage)
    monkeypatch.setattr("app.api.chat.get_storage", lambda: storage)
    try:
        # Freeze the legacy schema instead of downgrading irreversible role migrations.
        async with engine.begin() as connection:
            legacy = await seed_legacy_audit(connection, include_security_events=False)
            session_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO auth_sessions(id,user_id,created_at,expires_at) "
                    "VALUES (:id,:user,now(),now()+interval '1 day')"
                ),
                {"id": session_id, "user": legacy["user"]},
            )
        task = {"id": str(legacy["task"]), "reporter_id": str(legacy["user"])}
        owner = member = {
            "Authorization": "Bearer " + create_access_token(legacy["user"], session_id)
        }
        attachment_id, comment_id = uuid4(), uuid4()
        payload = b"legacy attachment bytes"
        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO comments (id, task_id, author_id, request_id, fingerprint, "
                    "sequence, text, created_at) VALUES "
                    "(:id,:task,:author,:request,:fingerprint,1,'legacy',now())"
                ),
                {
                    "id": comment_id,
                    "task": UUID(task["id"]),
                    "author": UUID(task["reporter_id"]),
                    "request": uuid4(),
                    "fingerprint": "0" * 64,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO attachments (id,comment_id,filename,media_type,size,content) "
                    "VALUES (:id,:comment,'legacy.txt','text/plain',:size,:content)"
                ),
                {
                    "id": attachment_id,
                    "comment": comment_id,
                    "size": len(payload),
                    "content": payload,
                },
            )
            await session.commit()
        migrate(url, "0015_attachment_objects")
        refused = migrate(url, "head", check=False)
        assert refused.returncode != 0 and "Run attachment migrate" in refused.stderr
        async with factory() as session:
            maintenance = AttachmentMaintenance(session, storage)
            original = storage.copy_to
            monkeypatch.setattr(storage, "copy_to", lambda *args: (len(payload), "0" * 64))
            with pytest.raises(ConflictError):
                await maintenance.migrate_one()
            await session.rollback()
            assert (
                await session.scalar(
                    text("SELECT content FROM attachments WHERE id=:id"), {"id": attachment_id}
                )
                == payload
            )
            monkeypatch.setattr(storage, "copy_to", original)
            assert await maintenance.migrate_one()
            assert not await maintenance.migrate_one()
            row = await maintenance.repository.locked(attachment_id)
            key, digest = row.object_key, row.sha256
            assert row.comment_id == comment_id and row.filename == "legacy.txt"
            assert row.state == "pending"
            await session.rollback()
            assert await maintenance.cleanup() >= 1  # Failed verification's abandoned object.
            assert storage.client.stat_object(storage.bucket, key).size == len(payload)
        # Before contract, the retained legacy bytes allow a schema rollback.
        migrate(url, "0014_auth_sessions", "downgrade")
        migrate(url, "0015_attachment_objects")
        async with factory() as session:
            maintenance = AttachmentMaintenance(session, storage)
            assert await maintenance.migrate_one()
            assert not await maintenance.migrate_one()
            assert await maintenance.cleanup() == 1
        migrate(url, "0017_attachment_scan_index")
        migrate(url, "0015_attachment_objects", "downgrade")
        migrate(url, "head")
        assert (
            await client.get(f"/api/attachments/{attachment_id}/content", headers=owner)
        ).status_code == 404
        uploaded = await post(client, task, owner, files=[("files", ("new.txt", b"new"))])
        assert uploaded.status_code == 201
        # Concurrent scanners claim distinct rows; rollback makes a claim retryable.
        from app.repositories.attachment_storage import AttachmentStorageRepository

        async with factory() as first, factory() as second:
            claimed = await AttachmentStorageRepository(first).next_pending()
            other = await asyncio.wait_for(AttachmentStorageRepository(second).next_pending(), 2)
            assert claimed is not None and other is not None
            assert claimed.id != other.id
            claimed_id = claimed.id
            await first.rollback()
            await second.rollback()
            retried = await AttachmentStorageRepository(second).next_pending()
            assert retried.id == claimed_id
            await second.rollback()
        # An in-flight publisher holds a shared transaction lock. Cleanup cannot
        # delete its object until publication commits or rolls back.
        incomplete_key = "attachments/" + str(uuid4())
        upload_id = storage.client._create_multipart_upload(storage.bucket, incomplete_key, {})
        storage.client._upload_part(storage.bucket, incomplete_key, b"part", {}, upload_id, 1)
        pending_key = "attachments/" + str(uuid4())
        async with factory() as publishing, factory() as cleaning:
            await ChatRepository(publishing).storage_lock()
            storage.put(pending_key, io.BytesIO(b"orphan"), 6)
            worker = asyncio.create_task(AttachmentMaintenance(cleaning, storage).cleanup())
            await asyncio.sleep(0.1)
            assert not worker.done()
            assert storage.client.stat_object(storage.bucket, pending_key).size == 6
            await publishing.rollback()
            assert await asyncio.wait_for(worker, 5) == 1
            assert (
                storage.client._list_multipart_uploads(
                    storage.bucket, prefix="attachments/"
                ).uploads
                == []
            )
        # Runtime review requires the current audit schema; legacy transfer remains usable at 0015.
        async with factory() as session:
            maintenance = AttachmentMaintenance(session, storage)
            await maintenance.review(attachment_id, digest, "ready")
            response = await client.get(f"/api/attachments/{attachment_id}/content", headers=member)
            assert response.content == payload
    finally:
        await engine.dispose()


@pytest.mark.skipif(os.getenv("RUN_ATTACHMENT_STACK") != "1", reason="Opt-in full container build")
async def test_compose_http_upload_review_and_download(deployment):
    from httpx import AsyncClient
    from pwdlib import PasswordHash

    from app.models import OrganizationMember, User, UserProfile

    compose, _, url, _ = deployment
    migrate(url, "head")
    compose(
        "up",
        "-d",
        "--build",
        "--wait",
        "--wait-timeout",
        "180",
        "backend",
        "frontend",
        "attachment-cleanup-worker",
    )
    endpoint = compose("port", "frontend", "80").strip()
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    email = f"{uuid4()}@example.com"
    password = "correct horse battery staple"
    try:
        async with factory() as session:
            user = User(
                is_system_admin=True,
                email=email,
                password_hash=PasswordHash.recommended().hash(password),
                profile=UserProfile(first_name="Smoke", last_name="Test"),
            )
            session.add(user)
            await session.commit()
        async with AsyncClient(
            base_url="http://" + endpoint,
            timeout=30,
            headers={"Origin": "http://localhost:5173", "X-CSRF-Protection": "1"},
        ) as http:
            login = await http.post("/api/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200, login.text
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            organization = (
                await http.post(
                    "/api/organizations", headers=headers, json={"name": "Storage smoke"}
                )
            ).json()
            async with factory() as session:
                session.add(
                    OrganizationMember(organization_id=UUID(organization["id"]), user_id=user.id)
                )
                await session.commit()
            project = (
                await http.post(
                    "/api/projects",
                    headers=headers,
                    json={"organization_id": organization["id"], "name": "Files"},
                )
            ).json()
            statuses = (
                await http.get(f"/api/projects/{project['id']}/statuses", headers=headers)
            ).json()
            task = (
                await http.post(
                    f"/api/projects/{project['id']}/tasks",
                    headers=headers,
                    json={"title": "Attachment smoke", "status_id": statuses[0]["id"]},
                )
            ).json()
            payload = b"container upload bytes" * 100000
            response = await post(http, task, headers, files=[("files", ("smoke.txt", payload))])
            assert response.status_code == 201, response.text
            attachment_id = response.json()["attachments"][0]["id"]
            content_url = f"/api/attachments/{attachment_id}/content"
            assert (await http.get(content_url, headers=headers)).status_code == 404
            digest = hashlib.sha256(payload).hexdigest()
            compose(
                "exec",
                "-T",
                "backend",
                "python",
                "-m",
                "app.commands.attachments",
                "review",
                attachment_id,
                "--sha256",
                digest,
                "--state",
                "ready",
                "--reviewed-safe",
            )
            response = await http.get(content_url, headers=headers)
            assert response.status_code == 200 and response.content == payload
            assert "sandbox" in response.headers["content-security-policy"]
            assert response.headers["content-disposition"].startswith("attachment;")
            assert (await http.get(content_url)).status_code == 401
            if os.getenv("RUN_ATTACHMENT_SCAN_STACK") == "1":
                from test_attachment_scan_integration import EICAR

                compose(
                    "up",
                    "-d",
                    "--build",
                    "--wait",
                    "--wait-timeout",
                    "240",
                    "clamav",
                    "attachment-scan-worker",
                )
                scanned = await post(
                    http,
                    task,
                    headers,
                    files=[("files", ("clean.txt", b"clean")), ("files", ("eicar.txt", EICAR))],
                )
                assert scanned.status_code == 201, scanned.text
                for _ in range(60):
                    message = (
                        await http.get(
                            f"/api/tasks/{task['id']}/comments/{scanned.json()['id']}",
                            headers=headers,
                        )
                    ).json()
                    states = {item["filename"]: item["state"] for item in message["attachments"]}
                    if "pending" not in states.values():
                        break
                    await asyncio.sleep(0.5)
                assert states == {"clean.txt": "ready", "eicar.txt": "infected"}
                for item in message["attachments"]:
                    result = await http.get(
                        f"/api/attachments/{item['id']}/content", headers=headers
                    )
                    assert result.status_code == (200 if item["state"] == "ready" else 404)

    finally:
        await engine.dispose()
