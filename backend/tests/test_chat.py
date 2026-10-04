import io
import json
from uuid import uuid4

from httpx import AsyncClient
from PIL import Image
from test_task_domain import authenticate, create_organization, create_project


async def setup_chat(client):
    owner_key, member_key = uuid4(), uuid4()
    owner = await authenticate(client, owner_key)
    member = await authenticate(client, member_key)
    organization = await create_organization(client, owner, "Chat")
    project = await create_project(client, owner, organization["id"], "Chat project")
    joined = await client.post(
        f"/api/organizations/{organization['id']}/members",
        headers=owner,
        json={"email": f"{member_key}@example.com"},
    )
    member_id = joined.json()["id"]
    await client.post(
        f"/api/projects/{project['id']}/members",
        headers=owner,
        json={"email": f"{member_key}@example.com"},
    )
    statuses = (await client.get(f"/api/projects/{project['id']}/statuses", headers=owner)).json()
    task = (
        await client.post(
            f"/api/projects/{project['id']}/tasks",
            headers=owner,
            json={"title": "Discuss", "status_id": statuses[0]["id"]},
        )
    ).json()
    return owner, member, project, task, member_id


async def post(client, task, headers, text="Hello", mentions=None, request_id=None, files=None):
    return await client.post(
        f"/api/tasks/{task['id']}/comments",
        headers=headers,
        data={
            "metadata": json.dumps(
                {
                    "request_id": str(request_id or uuid4()),
                    "text": text,
                    "mention_ids": mentions or [],
                }
            )
        },
        files=files,
    )


async def test_chat_messages_mentions_notifications_and_idempotency(client: AsyncClient):
    owner, member, project, task, member_id = await setup_chat(client)
    await client.post(f"/api/tasks/{task['id']}/watchers", headers=member, json={})
    await client.patch(
        f"/api/tasks/{task['id']}",
        headers=owner,
        json={"assignee_id": member_id, "reporter_id": member_id},
    )
    request_id = uuid4()
    response = await post(
        client, task, owner, mentions=[member_id, member_id], request_id=request_id
    )
    assert response.status_code == 201, response.text
    assert response.json()["author"]["first_name"] == "Test"
    assert len(response.json()["mentions"]) == 1
    duplicate = await post(client, task, owner, mentions=[member_id], request_id=request_id)
    assert duplicate.json()["id"] == response.json()["id"]
    assert (
        await post(client, task, owner, text="Changed", request_id=request_id)
    ).status_code == 409
    notifications = (await client.get("/api/notifications", headers=member)).json()
    chat = [item for item in notifications if item["event_type"] == "comment_created"]
    assert len(chat) == 1
    assert json.loads(chat[0]["event_data"])["comment_id"] == response.json()["id"]
    assert not [
        item
        for item in (await client.get("/api/notifications", headers=owner)).json()
        if item["event_type"] == "comment_created"
    ]
    await post(client, task, member, text="Reply")
    # The original technical author no longer has a notification role.
    assert not [
        item
        for item in (await client.get("/api/notifications", headers=owner)).json()
        if item["event_type"] == "comment_created"
    ]
    assert (await post(client, task, member, mentions=[str(uuid4())])).status_code == 422
    assert (await post(client, task, member, text=" ")).status_code == 422
    url = f"/api/tasks/{task['id']}/comments/{response.json()['id']}"
    assert (await client.patch(url, headers=owner, json={"text": "edit"})).status_code == 405
    assert (await client.delete(url, headers=owner)).status_code == 405


async def test_chat_cursor_and_private_attachments(
    client: AsyncClient, db_session, attachment_storage
):
    owner, member, project, task, member_id = await setup_chat(client)
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, format="PNG")
    created = await post(
        client,
        task,
        owner,
        text="",
        files=[
            ("files", ("picture.txt", image.getvalue(), "text/plain")),
            ("files", ("unsafe.svg", b'<svg onload="alert(1)"></svg>', "image/svg+xml")),
        ],
    )
    assert created.status_code == 201, created.text
    attachments = created.json()["attachments"]
    from uuid import UUID

    from app.models import Attachment
    from app.services.attachment_maintenance import AttachmentMaintenance

    maintenance = AttachmentMaintenance(db_session, attachment_storage)
    for item in attachments:
        row = await db_session.get(Attachment, UUID(item["id"]))
        await maintenance.review(row.id, row.sha256, "ready")
    assert attachments[0]["media_type"] == "image/png"
    assert attachments[1]["media_type"] == "application/octet-stream"
    for i in range(52):
        assert (await post(client, task, member, text=str(i))).status_code == 201
    url = f"/api/tasks/{task['id']}/comments"
    newest = (await client.get(url, headers=member)).json()
    assert len(newest["comments"]) == 50
    assert newest["has_more"]
    older = (
        await client.get(url, headers=member, params={"before": newest["comments"][0]["sequence"]})
    ).json()
    assert len(older["comments"]) == 3
    assert not older["has_more"]
    assert (await client.get(url, headers=member, params={"after": 53})).json()["comments"] == []
    assert (await client.get(f"{url}/{created.json()['id']}", headers=member)).status_code == 200
    download = f"/api/attachments/{attachments[0]['id']}/content"
    result = await client.get(download, headers=member, params={"preview": True})
    assert result.content == image.getvalue()
    assert "inline" in result.headers["content-disposition"]
    unsafe = await client.get(
        f"/api/attachments/{attachments[1]['id']}/content?preview=true", headers=member
    )
    assert "attachment" in unsafe.headers["content-disposition"]
    outsider = await authenticate(client, uuid4())
    assert (await client.get(url, headers=outsider)).status_code == 404
    assert (await client.get(download, headers=outsider)).status_code == 404
    await client.delete(f"/api/projects/{project['id']}/members/{member_id}", headers=owner)
    assert (await client.get(url, headers=member)).status_code == 200
    assert (await client.get(download, headers=member)).status_code == 200
    organization_message = await post(
        client,
        task,
        member,
        text="Organization-only reply",
        mentions=[task["reporter_id"]],
        files=[("files", ("note.txt", b"organization attachment"))],
    )
    assert organization_message.status_code == 201, organization_message.text
    assert len(organization_message.json()["attachments"]) == 1
    owner_notifications = (await client.get("/api/notifications", headers=owner)).json()
    assert any(
        item["event_type"] == "comment_created" and item["task_id"] == task["id"]
        for item in owner_notifications
    )
    assert (await client.get(download)).status_code == 401


async def test_chat_file_limits(client: AsyncClient):
    owner, _, _, task, _ = await setup_chat(client)
    data = b"x" * (25 * 1024 * 1024)
    ok = await post(client, task, owner, text="", files=[("files", ("file.bin", data))])
    assert ok.status_code == 201, ok.text
    large = await post(client, task, owner, files=[("files", ("file.bin", data + b"x"))])
    assert large.status_code == 413
    too_many = await post(client, task, owner, files=[("files", ("a", b"x"))] * 6)
    assert too_many.status_code == 422
    assert (
        await client.post(
            f"/api/tasks/{task['id']}/comments",
            headers={**owner, "Content-Length": str(131 * 1024 * 1024)},
            content=b"x",
        )
    ).status_code == 413


async def test_streamed_upload_limit_and_transaction_rollback(client: AsyncClient, monkeypatch):
    import app.api.upload_limit as limits
    import app.services.attachment_files as chat

    owner, _, _, task, _ = await setup_chat(client)
    monkeypatch.setattr(limits, "MAX_REQUEST", 128)

    async def chunks():
        yield b'--boundary\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'
        yield b"x" * 256
        yield b"\r\n--boundary--\r\n"

    streamed = await client.post(
        f"/api/tasks/{task['id']}/comments",
        headers={**owner, "Content-Type": "multipart/form-data; boundary=boundary"},
        content=chunks(),
    )
    assert streamed.status_code == 413
    monkeypatch.setattr(limits, "MAX_REQUEST", 130 * 1024 * 1024)

    def broken_inspection(_):
        raise RuntimeError("Simulated file inspection failure")

    monkeypatch.setattr(chat, "media_type", broken_inspection)
    import pytest

    with pytest.raises(RuntimeError, match="inspection failure"):
        await post(client, task, owner, files=[("files", ("file.txt", b"data"))])
    response = await client.get(f"/api/tasks/{task['id']}/comments", headers=owner)
    assert response.json()["comments"] == []
    assert (await client.get("/api/notifications", headers=owner)).json() == []
