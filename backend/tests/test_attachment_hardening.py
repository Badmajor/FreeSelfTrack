import asyncio
import hashlib
import io
from uuid import UUID, uuid4

import pytest
from PIL import Image
from sqlalchemy import select
from test_chat import post, setup_chat
from test_task_domain import authenticate, create_organization

from app.api.upload_limit import ChatUploadLimit
from app.core.config import get_settings
from app.core.object_storage import CHUNK_SIZE, StorageUnavailable
from app.models import Attachment
from app.services.attachment_files import inspect_file
from app.services.attachment_maintenance import AttachmentMaintenance
from app.services.errors import ConflictError, InvalidWorkflowError


async def test_quarantine_review_integrity_and_idempotent_upload(
    client, db_session, attachment_storage
):
    owner, member, _, task, _ = await setup_chat(client)
    request_id = uuid4()
    files = [("files", ("../bad\x7fname.svg", b"<svg/>", "image/svg+xml"))]
    created = await post(client, task, owner, request_id=request_id, files=files)
    assert created.status_code == 201
    file = created.json()["attachments"][0]
    assert file["state"] == "pending"
    assert file["filename"] == "badname.svg"
    assert file["media_type"] == "application/octet-stream"
    assert "object_key" not in file and "sha256" not in file
    url = f"/api/attachments/{file['id']}/content"
    assert (await client.get(url, headers=member)).status_code == 404
    assert attachment_storage.opens == 0
    duplicate = await post(client, task, owner, request_id=request_id, files=files)
    assert duplicate.json()["id"] == created.json()["id"]
    assert len(attachment_storage.objects) == 1
    row = await db_session.get(Attachment, UUID(file["id"]))
    maintenance = AttachmentMaintenance(db_session, attachment_storage)
    with pytest.raises(ConflictError):
        await maintenance.review(row.id, "0" * 64, "ready")
    await db_session.rollback()
    digest = hashlib.sha256(b"<svg/>").hexdigest()
    await maintenance.review(UUID(file["id"]), digest, "ready")
    result = await client.get(url + "?preview=true", headers=member)
    assert result.content == b"<svg/>"
    assert result.headers["content-disposition"].startswith("attachment;")
    assert result.headers["cache-control"] == "private, no-store"
    assert result.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in result.headers["content-security-policy"]
    await maintenance.review(UUID(file["id"]), digest, "infected")
    assert (await client.get(url, headers=owner)).status_code == 404
    with pytest.raises(ConflictError):
        await maintenance.review(UUID(file["id"]), digest, "ready")


async def test_attachment_organization_revocation_and_soft_delete(
    client, db_session, attachment_storage
):
    owner, member, project, task, member_id = await setup_chat(client)
    created = await post(client, task, owner, files=[("files", ("a", b"hello"))])
    row = await db_session.get(Attachment, UUID(created.json()["attachments"][0]["id"]))
    await AttachmentMaintenance(db_session, attachment_storage).review(row.id, row.sha256, "ready")
    url = f"/api/attachments/{row.id}/content"
    outsider = await authenticate(client, uuid4())
    await create_organization(client, outsider, "Other organization")
    before = attachment_storage.opens
    assert (await client.get(url, headers=outsider)).status_code == 404
    assert (await client.get(url)).status_code == 401
    assert attachment_storage.opens == before
    organization_id = project["organization_id"]
    removed = await client.delete(
        f"/api/organizations/{organization_id}/members/{member_id}", headers=owner
    )
    assert removed.status_code == 200
    assert (await client.get(url, headers=member)).status_code == 404
    assert (
        await client.request(
            "DELETE", f"/api/projects/{project['id']}", headers=owner, json={"confirm": True}
        )
    ).status_code == 204
    assert (await client.get(url, headers=owner)).status_code == 404
    assert (await client.delete(url, headers=owner)).status_code == 405


async def test_storage_outage_commit_failure_and_cleanup(
    client, db_session, attachment_storage, monkeypatch
):
    owner, _, _, task, _ = await setup_chat(client)
    original = attachment_storage.put

    def fail(*_):
        raise StorageUnavailable()

    monkeypatch.setattr(attachment_storage, "put", fail)
    failed = await post(client, task, owner, files=[("files", ("a", b"x"))])
    assert failed.status_code == 503
    assert "minio" not in failed.text
    monkeypatch.setattr(attachment_storage, "put", original)
    from sqlalchemy.ext.asyncio import AsyncSession

    commit = AsyncSession.commit

    async def broken_commit(self):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(AsyncSession, "commit", broken_commit)
    with pytest.raises(RuntimeError, match="simulated DB failure"):
        await post(client, task, owner, files=[("files", ("a", b"x"))])
    monkeypatch.setattr(AsyncSession, "commit", commit)
    assert len(attachment_storage.objects) == 1
    assert (await client.get(f"/api/tasks/{task['id']}/comments", headers=owner)).json()[
        "comments"
    ] == []
    maintenance = AttachmentMaintenance(db_session, attachment_storage)
    assert await maintenance.cleanup() == 1
    good = await post(client, task, owner, files=[("files", ("a", b"x"))])
    assert good.status_code == 201
    assert await maintenance.cleanup() == 0
    assert len(attachment_storage.objects) == 1
    row = await db_session.scalar(select(Attachment))
    await maintenance.review(row.id, row.sha256, "ready")
    attachment_storage.objects.clear()
    assert (
        await client.get(f"/api/attachments/{row.id}/content", headers=owner)
    ).status_code == 503


@pytest.mark.parametrize("kind", ["PNG", "JPEG", "GIF", "WEBP"])
def test_verified_rasters_ignore_claimed_mime(kind):
    source = io.BytesIO()
    Image.new("RGB", (2, 2)).save(source, kind)
    result = inspect_file("image.html", source)
    assert result.media_type == "image/" + ("jpeg" if kind == "JPEG" else kind.lower())


def test_validation_is_bounded_and_rejects_pixel_bombs(monkeypatch):
    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert 0 <= size <= CHUNK_SIZE
            return super().read(size)

    result = inspect_file("\u202e../file\x00.bin", Bounded(b"x" * (CHUNK_SIZE + 9)))
    assert result.size == CHUNK_SIZE + 9
    assert result.filename == "file.bin"
    image = io.BytesIO()
    Image.new("RGB", (3, 3)).save(image, "PNG")
    monkeypatch.setattr("app.services.attachment_files.MAX_PIXELS", 4)
    with pytest.raises(InvalidWorkflowError):
        inspect_file("bomb.png", image)
    with pytest.raises(InvalidWorkflowError):
        inspect_file("broken.png", io.BytesIO(b"\x89PNG\r\n\x1a\ntruncated"))


async def test_invalid_images_do_not_publish(client, monkeypatch):
    owner, _, _, task, _ = await setup_chat(client)
    response = await post(
        client, task, owner, files=[("files", ("broken.png", b"\x89PNG\r\n\x1a\n"))]
    )
    assert response.status_code == 422
    assert (await client.get(f"/api/tasks/{task['id']}/comments", headers=owner)).json()[
        "comments"
    ] == []


async def test_admission_limit_before_multipart_and_slots_recover(monkeypatch):
    monkeypatch.setattr(get_settings(), "attachment_upload_slots", 1)
    entered, release = asyncio.Event(), asyncio.Event()

    async def application(scope, receive, send):
        entered.set()
        await release.wait()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ChatUploadLimit(application)

    async def receive():
        raise AssertionError("Excess request must not read its body")

    messages = []

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/tasks/id/comments", "headers": []}
    first = asyncio.create_task(middleware(scope, receive, send))
    await entered.wait()
    await middleware(scope, receive, send)
    assert messages[0]["status"] == 429
    release.set()
    await first
    await middleware(scope, receive, send)
    assert messages[-2]["status"] == 204
    assert middleware.uploads == 0


async def test_idle_upload_timeout_and_temp_storage_error(client, monkeypatch):
    owner, _, _, task, _ = await setup_chat(client)
    monkeypatch.setattr(get_settings(), "attachment_idle_seconds", 0.01)

    async def slow_body():
        await asyncio.sleep(0.1)
        yield b"body"

    result = await client.post(
        f"/api/tasks/{task['id']}/comments",
        headers={**owner, "Content-Type": "multipart/form-data; boundary=slow"},
        content=slow_body(),
    )
    assert result.status_code == 408
    monkeypatch.setattr(get_settings(), "attachment_idle_seconds", 30)

    def no_disk(*_):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.chat.inspect_file", no_disk)
    result = await post(client, task, owner, files=[("files", ("a", b"hello"))])
    assert result.status_code == 503
    assert "disk full" not in result.text


async def test_multiple_files_keep_input_order(client):
    owner, _, _, task, _ = await setup_chat(client)
    filenames = ["z.txt", "a.txt", "middle.txt"]
    created = await post(
        client, task, owner, files=[("files", (name, name.encode())) for name in filenames]
    )
    assert created.status_code == 201
    assert [file["filename"] for file in created.json()["attachments"]] == filenames
    loaded = await client.get(
        f"/api/tasks/{task['id']}/comments/{created.json()['id']}", headers=owner
    )
    assert [file["filename"] for file in loaded.json()["attachments"]] == filenames


async def test_download_closes_storage_on_client_disconnect(monkeypatch, attachment_storage):
    from types import SimpleNamespace

    from starlette.requests import ClientDisconnect
    from urllib3.response import HTTPResponse

    from app.api.chat import attachment
    from app.services.chat import ChatService

    async def authorized(*_):
        return SimpleNamespace(
            object_key="attachments/test",
            filename="a.txt",
            media_type="application/octet-stream",
            size=3,
        )

    monkeypatch.setattr(ChatService, "attachment", authorized)
    body = HTTPResponse(body=io.BytesIO(b"abc"), preload_content=False)
    monkeypatch.setattr(attachment_storage, "open", lambda _: body)
    response = await attachment(uuid4(), False, uuid4(), None)

    async def send(_):
        raise OSError("client disconnected")

    async def receive():
        return {"type": "http.disconnect"}

    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert body.closed


async def test_download_disconnect_listener_has_no_upload_idle_timeout(monkeypatch):
    monkeypatch.setattr(get_settings(), "attachment_idle_seconds", 0.01)

    async def application(scope, receive, send):
        listener = asyncio.create_task(receive())
        try:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            for _ in range(4):
                await asyncio.sleep(0.006)
                await send({"type": "http.response.body", "body": b"x", "more_body": True})
            assert not listener.done()
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            listener.cancel()
            with pytest.raises(asyncio.CancelledError):
                await listener

    async def receive():
        await asyncio.Event().wait()

    messages = []

    async def send(message):
        messages.append(message)

    middleware = ChatUploadLimit(application)
    await middleware(
        {"type": "http", "method": "GET", "path": "/api/attachments/id/content", "headers": []},
        receive,
        send,
    )
    assert len(messages) == 6 and middleware.downloads == 0
