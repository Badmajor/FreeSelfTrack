# ruff: noqa: F811
"""Archive access, atomic lifecycle, immutable data and worker suppression."""

from datetime import date
from uuid import UUID

import pytest
from auth_helpers import authenticated_id
from sqlalchemy import func, select
from test_chat import post
from test_task_access import matrix  # noqa: F401

from app.models import (
    AdministrativeAuditEvent,
    OrganizationMember,
    ProjectMember,
    Task,
    TaskHistory,
)
from app.services.administration import AdministrationService
from app.services.administrative_audit import AdministrativeAuditService
from app.services.deadlines import DeadlineService


async def lifecycle(client, headers, scope, identifier, action="archive"):
    return await client.post(
        f"/api/{scope}s/{identifier}/{action}",
        headers=headers,
        **({"json": {"confirm": True}} if action == "archive" else {}),
    )


async def test_project_cascade_retains_read_then_revokes_memberships(client, db_session, matrix):  # noqa: F811
    actors, projects, tasks = matrix
    project, task = projects[0], tasks[0]
    before = (await client.get(f"/api/tasks/{task['id']}", headers=actors["sa"])).json()
    assert (await lifecycle(client, actors["pm"], "project", project["id"])).status_code == 403
    response = await lifecycle(client, actors["om"], "project", project["id"])
    assert response.status_code == 200, response.text
    assert response.json()["archived_at"]
    after = (await client.get(f"/api/tasks/{task['id']}", headers=actors["employee"])).json()
    assert after["archived_at"]
    for field in ("status_id", "created_by", "reporter_id", "assignee_id", "updated_at"):
        assert after[field] == before[field]
    assert not after["capabilities"]["edit"] and not after["capabilities"]["comment"]
    uid = authenticated_id(actors["pm"])
    db_session.expire_all()
    member = await db_session.get(
        ProjectMember, {"project_id": UUID(project["id"]), "user_id": uid}
    )
    assert (member.state, member.role) == ("archived", "manager")
    assert await AdministrationService(db_session).level(uid) == 0
    for role in ("sa", "om", "pm", "employee"):
        assert (
            await client.patch(
                f"/api/tasks/{task['id']}", headers=actors[role], json={"title": "No"}
            )
        ).status_code == 409
        assert (await post(client, task, actors[role], text="No")).status_code == 409
    assert (
        await client.get(f"/api/tasks/{task['id']}", headers=actors["revoked"])
    ).status_code == 404
    assert (
        await client.get(f"/api/projects/{projects[1]['id']}", headers=actors["pm"])
    ).status_code == 404
    count = await db_session.scalar(
        select(func.count())
        .select_from(AdministrativeAuditEvent)
        .where(AdministrativeAuditEvent.action == "archived")
    )
    assert count == 2
    assert (await lifecycle(client, actors["om"], "project", project["id"])).status_code == 200
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AdministrativeAuditEvent)
            .where(AdministrativeAuditEvent.action == "archived")
        )
        == count
    )
    assert (await lifecycle(client, actors["sa"], "task", task["id"], "restore")).status_code == 409
    assert (
        await lifecycle(client, actors["om"], "project", project["id"], "restore")
    ).status_code == 200
    assert (
        await client.get(f"/api/tasks/{task['id']}", headers=actors["employee"])
    ).status_code == 404
    assert (await client.get(f"/api/tasks/{task['id']}", headers=actors["sa"])).json()[
        "archived_at"
    ]
    assert (await lifecycle(client, actors["om"], "task", task["id"], "restore")).status_code == 200
    db_session.expire_all()
    member = await db_session.get(
        ProjectMember, {"project_id": UUID(project["id"]), "user_id": uid}
    )
    assert (member.state, member.role) == ("revoked", "member")
    assert await db_session.scalar(select(func.count()).select_from(TaskHistory)) == 0


async def test_org_restore_revokes_even_previously_archived_projects(client, db_session, matrix):  # noqa: F811
    actors, projects, tasks = matrix
    organization_id = projects[0]["organization_id"]
    assert (
        await lifecycle(client, actors["om"], "organization", organization_id)
    ).status_code == 403
    await lifecycle(client, actors["sa"], "project", projects[0]["id"])
    await lifecycle(client, actors["sa"], "organization", organization_id)
    assert (
        await client.get(f"/api/tasks/{tasks[0]['id']}", headers=actors["employee"])
    ).status_code == 200
    # Archived OM retains global archived reading, but loses global active reading.
    assert (
        await client.get(f"/api/tasks/{tasks[2]['id']}", headers=actors["om"])
    ).status_code == 404
    await lifecycle(client, actors["sa"], "task", tasks[2]["id"])
    assert (
        await client.get(f"/api/tasks/{tasks[2]['id']}", headers=actors["om"])
    ).status_code == 200
    assert (
        await lifecycle(client, actors["sa"], "project", projects[0]["id"], "restore")
    ).status_code == 409
    restored = await lifecycle(client, actors["sa"], "organization", organization_id, "restore")
    assert restored.status_code == 200
    for project in projects[:2]:
        assert (await client.get(f"/api/projects/{project['id']}", headers=actors["sa"])).json()[
            "archived_at"
        ]
    for task in tasks:
        assert (
            await client.get(f"/api/tasks/{task['id']}", headers=actors["om"])
        ).status_code == 404
    db_session.expire_all()
    grants = list(
        await db_session.scalars(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == UUID(organization_id)
            )
        )
    )
    assert all(grant.state == "revoked" and grant.role == "member" for grant in grants)
    project_grants = list(
        await db_session.scalars(
            select(ProjectMember).where(
                ProjectMember.project_id.in_([UUID(p["id"]) for p in projects[:2]])
            )
        )
    )
    assert all(grant.state == "revoked" and grant.role == "member" for grant in project_grants)
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AdministrativeAuditEvent)
            .where(AdministrativeAuditEvent.action == "restored")
        )
        == 1
    )


@pytest.mark.parametrize("field", ["created_by", "reporter_id", "assignee_id"])
async def test_employee_lifecycle_requires_identity_and_active_membership(
    client, db_session, matrix, field
):  # noqa: F811
    actors, _, tasks = matrix
    task = tasks[0]
    assert (await lifecycle(client, actors["employee"], "task", task["id"])).status_code == 403
    row = await db_session.get(Task, UUID(task["id"]))
    setattr(row, field, authenticated_id(actors["employee"]))
    await db_session.commit()
    assert (await lifecycle(client, actors["employee"], "task", task["id"])).status_code == 200
    assert (
        await lifecycle(client, actors["employee"], "task", task["id"], "restore")
    ).status_code == 200


async def test_filters_pagination_and_worker(client, db_session, matrix):  # noqa: F811
    actors, projects, tasks = matrix
    task = tasks[0]
    row = await db_session.get(Task, UUID(task["id"]))
    row.assignee_id = authenticated_id(actors["employee"])
    row.due_date = date(2020, 1, 1)
    await db_session.commit()
    await lifecycle(client, actors["sa"], "task", task["id"])
    assert await DeadlineService(db_session).process_due(date(2030, 1, 1)) == 0
    for state, expected in (("active", 0), ("archived", 1), ("all", 1)):
        response = await client.get(
            f"/api/projects/{projects[0]['id']}/tasks?state={state}", headers=actors["employee"]
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == expected
        board = (
            await client.get(
                f"/api/projects/{projects[0]['id']}/board?state={state}", headers=actors["employee"]
            )
        ).json()
        assert sum(len(column["tasks"]) for column in board["columns"]) == expected
    page = (await client.get("/api/organizations?limit=1", headers=actors["sa"])).json()
    assert page["next_cursor"]
    assert (
        await client.get(
            "/api/organizations",
            params={"cursor": page["next_cursor"], "state": "archived"},
            headers=actors["sa"],
        )
    ).status_code == 422
    assert (
        await client.delete(f"/api/projects/{projects[0]['id']}", headers=actors["sa"])
    ).status_code == 404


async def test_failed_audit_rolls_back_cascade(client, db_session, matrix, monkeypatch):  # noqa: F811
    actors, projects, tasks = matrix
    original = AdministrativeAuditService.record
    calls = 0

    def failing(self, event):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("audit unavailable")
        return original(self, event)

    monkeypatch.setattr(AdministrativeAuditService, "record", failing)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await lifecycle(client, actors["sa"], "project", projects[0]["id"])
    response = await client.get(f"/api/tasks/{tasks[0]['id']}", headers=actors["employee"])
    assert response.status_code == 200 and response.json()["archived_at"] is None
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AdministrativeAuditEvent)
            .where(AdministrativeAuditEvent.action == "archived")
        )
        == 0
    )


async def test_archive_pauses_scan_keeps_ready_files_and_assignee(
    client, db_session, matrix, attachment_storage
):  # noqa: F811
    from test_attachment_scanning import VerdictScanner

    from app.models import Attachment
    from app.services.attachment_maintenance import AttachmentMaintenance
    from app.services.attachment_scanning import AttachmentScanning
    from app.services.errors import ConflictError

    actors, projects, tasks = matrix
    task = tasks[0]
    created = await post(
        client,
        task,
        actors["sa"],
        files=[("files", ("ready.txt", b"ready")), ("files", ("pending.txt", b"pending"))],
    )
    first, second = created.json()["attachments"]
    row = await db_session.get(Attachment, UUID(first["id"]))
    await AttachmentMaintenance(db_session, attachment_storage).review(row.id, row.sha256, "ready")
    row = await db_session.get(Task, UUID(task["id"]))
    row.assignee_id = authenticated_id(actors["employee"])
    await db_session.commit()
    assert (await lifecycle(client, actors["sa"], "project", projects[0]["id"])).status_code == 200
    body = (await client.get(f"/api/tasks/{task['id']}", headers=actors["employee"])).json()
    assert body["assignee"]["unavailable_reasons"] == []
    assert (
        await client.get(f"/api/attachments/{first['id']}/content", headers=actors["employee"])
    ).status_code == 200
    assert (
        await AttachmentScanning(
            db_session, attachment_storage, VerdictScanner("ready")
        ).scan_next()
        is None
    )
    pending = await db_session.get(Attachment, UUID(second["id"]))
    with pytest.raises(ConflictError, match="Restore"):
        await AttachmentMaintenance(db_session, attachment_storage).review(
            pending.id, pending.sha256, "ready"
        )
    await db_session.rollback()
    await lifecycle(client, actors["sa"], "project", projects[0]["id"], "restore")
    body = (await client.get(f"/api/tasks/{task['id']}", headers=actors["sa"])).json()
    assert body["assignee"]["unavailable_reasons"] == ["project_membership_revoked"]
    uid = authenticated_id(actors["employee"])
    added = await client.put(
        f"/api/projects/{projects[0]['id']}/members/{uid}",
        headers=actors["sa"],
        json={"role": "member"},
    )
    assert added.status_code == 200
    # Same-state restore must not revoke newly granted membership.
    await lifecycle(client, actors["sa"], "project", projects[0]["id"], "restore")
    body = (await client.get(f"/api/tasks/{task['id']}", headers=actors["employee"])).json()
    assert body["assignee"]["unavailable_reasons"] == []
    assert (
        await AttachmentScanning(
            db_session, attachment_storage, VerdictScanner("ready")
        ).scan_next()
        is None
    )
    await lifecycle(client, actors["sa"], "task", task["id"], "restore")
    assert await AttachmentScanning(
        db_session, attachment_storage, VerdictScanner("ready")
    ).scan_next() == UUID(second["id"])


async def test_archived_links_are_read_only_and_filter_inaccessible_second_side(
    client, db_session, matrix
):  # noqa: F811
    actors, projects, tasks = matrix
    link = await client.post(
        f"/api/tasks/{tasks[0]['id']}/links",
        headers=actors["sa"],
        json={"target_task_id": tasks[1]["id"], "relation_type": "related"},
    )
    assert link.status_code == 201
    await lifecycle(client, actors["sa"], "project", projects[0]["id"])
    # Archived PM no longer reads the active other project or leaks it via link history.
    for path, key in (("links", None), ("history", "entries")):
        response = await client.get(f"/api/tasks/{tasks[0]['id']}/{path}", headers=actors["pm"])
        assert response.status_code == 200
        assert (response.json()[key] if key else response.json()) == []
    response = await client.get(f"/api/tasks/{tasks[0]['id']}/links", headers=actors["sa"])
    assert len(response.json()) == 1 and not response.json()[0]["can_delete"]
    assert (
        await client.delete(
            f"/api/tasks/{tasks[0]['id']}/links/{link.json()['id']}", headers=actors["sa"]
        )
    ).status_code == 409
    await lifecycle(client, actors["sa"], "task", tasks[1]["id"])
    assert (
        len((await client.get(f"/api/tasks/{tasks[0]['id']}/links", headers=actors["pm"])).json())
        == 1
    )
