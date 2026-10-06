"""Audit behavior through the same services and HTTP boundaries used by the application."""

from uuid import UUID, uuid4

import pytest
from auth_helpers import authenticated_id, set_system_admin
from sqlalchemy import func, select
from test_chat import post, setup_chat
from test_task_domain import authenticate, create_organization, create_project

from app.main import app
from app.models import Organization, SecurityEvent, Task, TaskHistory
from app.schemas.domain import OrganizationCreate, TaskUpdate
from app.services.attachment_maintenance import AttachmentMaintenance
from app.services.audit import record_event
from app.services.domain import DomainService


async def events(session, kind=None):
    query = select(SecurityEvent)
    if kind:
        query = query.where(SecurityEvent.event_type == kind)
    return list(await session.scalars(query))


async def test_login_failure_success_and_revocation(client, db_session):
    headers = await authenticate(client, uuid4())
    success = await events(db_session, "login_succeeded")
    assert len(success) == 1
    assert success[0].actor_id is not None
    assert success[0].target_type == "session"
    response = await client.post(
        "/api/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "secret-never-recorded",
        },
        headers={"X-Request-ID": "untrusted"},
    )
    assert response.status_code == 401
    failure = (await events(db_session, "login_failed"))[0]
    assert failure.actor_kind == "anonymous" and failure.actor_id is None
    assert failure.target_id is None and failure.organization_id is None
    assert str(failure.request_id) == response.headers["x-request-id"]
    assert failure.details == {}
    assert (await client.delete("/api/auth/sessions/current", headers=headers)).status_code == 204
    revoked = await events(db_session, "session_revoked")
    assert len(revoked) == 1
    assert revoked[0].target_id == success[0].target_id
    assert revoked[0].actor_id == success[0].actor_id
    assert len({e.id for e in await events(db_session)}) == 3


async def test_membership_ownership_lifecycle_and_idempotency(client, db_session):
    owner = await authenticate(client, uuid4())
    member_email_id = uuid4()
    member = await authenticate(client, member_email_id)
    org = await create_organization(client, owner, "Audit")
    project = await create_project(client, owner, org["id"], "Audit")
    for scope, identifier in [("organizations", org["id"]), ("projects", project["id"])]:
        for _ in range(2):
            response = await client.post(
                f"/api/{scope}/{identifier}/members",
                headers=owner,
                json={"email": f"{member_email_id}@example.com"},
            )
            assert response.status_code == 200
    added = await events(db_session, "membership_added")
    assert len(added) == 2  # Resource creation no longer adds the creator.
    assert all(e.organization_id == UUID(org["id"]) for e in added)
    for _ in range(2):
        response = await client.post(
            f"/api/projects/{project['id']}/transfer-ownership",
            headers=owner if _ == 0 else member,
            json={"email": f"{member_email_id}@example.com"},
        )
        assert response.status_code == 404
    assert len(await events(db_session, "ownership_transferred")) == 0
    await set_system_admin(owner)
    response = await client.request(
        "DELETE", f"/api/organizations/{org['id']}", headers=owner, json={"confirm": True}
    )
    assert response.status_code == 204
    deleted = await events(db_session, "resource_deleted")
    assert {e.target_id for e in deleted} == {UUID(org["id"]), UUID(project["id"])}
    assert len({e.request_id for e in deleted}) == 1
    assert (
        await client.post(f"/api/organizations/{org['id']}/restore", headers=owner)
    ).status_code == 200
    assert (
        await client.post(f"/api/projects/{project['id']}/restore", headers=owner)
    ).status_code == 200
    assert len(await events(db_session, "resource_restored")) == 2
    member_id = next(
        e.details["member_id"] for e in added if e.actor_id != UUID(e.details["member_id"])
    )
    # The new project owner removes the previous owner's project membership.
    response = await client.delete(
        f"/api/projects/{project['id']}/members/{authenticated_id(owner)}", headers=owner
    )
    assert response.status_code == 200
    response = await client.delete(
        f"/api/organizations/{org['id']}/members/{member_id}", headers=owner
    )
    assert response.status_code == 200
    removed = await events(db_session, "membership_removed")
    assert len(removed) == 2
    assert all(e.organization_id == UUID(org["id"]) for e in removed)


async def test_audit_failure_rolls_back_originating_mutation(client, db_session, monkeypatch):
    owner = await authenticate(client, uuid4())
    await create_organization(client, owner, "Existing")
    actor_id = authenticated_id(owner)
    await set_system_admin(owner)
    before = await db_session.scalar(select(func.count()).select_from(SecurityEvent))

    # An audit insert rejected at flush must not leave a committed organization.
    def fail_record(self, *args, **kwargs):
        self.repository.session.add(SecurityEvent(event_type=None))

    monkeypatch.setattr(
        "app.services.administrative_audit.AdministrativeAuditService.record", fail_record
    )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await DomainService(db_session).create_organization(
            actor_id, OrganizationCreate(name="Lost")
        )
    await db_session.rollback()
    assert await db_session.scalar(select(Organization).where(Organization.name == "Lost")) is None
    assert await db_session.scalar(select(func.count()).select_from(SecurityEvent)) == before


async def test_history_authorization_no_mutation_and_atomicity(client, db_session, monkeypatch):
    owner, member, project, task_data, _ = await setup_chat(client)
    task_id = task_data["id"]
    outsider = await authenticate(client, uuid4())
    url = f"/api/tasks/{task_id}/history"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=outsider)).status_code == 404
    assert (await client.get(f"/api/tasks/{uuid4()}/history", headers=owner)).status_code == 404
    assert (await client.get(url, headers=member)).status_code == 200
    for route in app.routes:
        if "history" in getattr(route, "path", ""):
            assert route.methods <= {"GET", "HEAD"}
    task = await db_session.get(Task, UUID(task_id))
    actor_id = task.created_by
    previous_title = task.title
    count = await db_session.scalar(select(func.count()).select_from(TaskHistory))

    async def fail_commit():
        await db_session.flush()
        raise RuntimeError("simulated transaction failure")

    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", fail_commit)
        with pytest.raises(RuntimeError):
            await DomainService(db_session).update_task(
                actor_id, UUID(task_id), TaskUpdate(title="Lost")
            )
    await db_session.rollback()
    task = await db_session.get(Task, UUID(task_id))
    assert task.title == previous_title
    assert await db_session.scalar(select(func.count()).select_from(TaskHistory)) == count
    response = await client.patch(f"/api/tasks/{task_id}", headers=owner, json={"title": "Changed"})
    assert response.status_code == 200
    assert len((await client.get(url, headers=owner)).json()["entries"]) == count + 1
    response = await client.request(
        "DELETE", f"/api/projects/{task.project_id}", headers=owner, json={"confirm": True}
    )
    assert response.status_code == 204
    assert (await client.get(url, headers=owner)).status_code == 404
    assert (await client.get(url, headers=member)).status_code == 404


async def test_attachment_audit_no_content_and_no_duplicate_review(
    client, db_session, attachment_storage
):
    owner, _, _, task, _ = await setup_chat(client)
    response = await post(
        client, task, owner, files=[("files", ("private-name.txt", b"private bytes"))]
    )
    attachment_id = UUID(response.json()["attachments"][0]["id"])
    from app.models import Attachment

    attachment = await db_session.get(Attachment, attachment_id)
    service = AttachmentMaintenance(db_session, attachment_storage)
    for _ in range(2):
        await service.review(attachment_id, attachment.sha256, "ready")
    rows = await events(db_session, "attachment_state_changed")
    assert len(rows) == 2
    assert rows[0].actor_kind == "user"
    assert rows[1].actor_kind == "attachment_operator"
    assert rows[1].details == {"previous_state": "pending", "state": "ready"}
    assert rows[0].organization_id == rows[1].organization_id
    assert rows[0].target_id == rows[1].target_id == attachment_id
    assert "private" not in str([row.details for row in rows])
    with pytest.raises(TypeError):
        record_event(
            db_session,
            "bad",
            actor_id=None,
            target_type="user",
            target_id=None,
            password="never accepted",
        )


async def test_organization_deletion_and_revoked_membership_hide_history(client):
    owner, member, project, task, member_id = await setup_chat(client)
    url = f"/api/tasks/{task['id']}/history"
    org_id = project["organization_id"]
    response = await client.delete(
        f"/api/organizations/{org_id}/members/{member_id}", headers=owner
    )
    assert response.status_code == 200
    assert (await client.get(url, headers=member)).status_code == 404
    await set_system_admin(owner)
    response = await client.request(
        "DELETE", f"/api/organizations/{org_id}", headers=owner, json={"confirm": True}
    )
    assert response.status_code == 204
    assert (await client.get(url, headers=owner)).status_code == 404


async def test_password_change_audits_every_revoked_session(client, db_session):
    key = uuid4()
    headers = await authenticate(client, key)
    response = await client.post(
        "/api/auth/login",
        json={"email": f"{key}@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    response = await client.post(
        "/api/auth/password/change",
        headers=headers,
        json={
            "current_password": "correct horse battery staple",
            "new_password": "another long safe test password",
        },
    )
    assert response.status_code == 204
    successes = await events(db_session, "login_succeeded")
    revoked = await events(db_session, "session_revoked")
    assert len(revoked) == 2
    assert {e.target_id for e in revoked} == {e.target_id for e in successes}
    assert len({e.request_id for e in revoked}) == 1
    assert all(e.actor_id == successes[0].actor_id and e.details == {} for e in revoked)


async def test_scanner_retries_do_not_append_audit_until_state_changes(
    client, db_session, attachment_storage
):
    from test_attachment_scanning import VerdictScanner

    from app.services.attachment_scanning import AttachmentScanning

    owner, _, _, task, _ = await setup_chat(client)
    response = await post(client, task, owner, files=[("files", ("safe.txt", b"safe"))])
    attachment_id = UUID(response.json()["attachments"][0]["id"])
    scanner = VerdictScanner("error")
    service = AttachmentScanning(db_session, attachment_storage, scanner)
    await service.scan_next()
    assert len(await events(db_session, "attachment_state_changed")) == 1
    scanner.verdict = "infected"
    await service.scan_next()
    assert await service.scan_next() is None
    rows = await events(db_session, "attachment_state_changed")
    assert len(rows) == 2
    assert rows[1].target_id == attachment_id
    assert rows[1].actor_kind == "attachment_scanner" and rows[1].actor_id is None
    assert rows[1].organization_id == rows[0].organization_id
    assert rows[1].details == {"previous_state": "pending", "state": "infected"}
