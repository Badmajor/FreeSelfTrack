"""TASK-034: resource scopes, read/write separation and revoked access."""

from uuid import UUID, uuid4

import pytest
from auth_helpers import authenticated_id
from test_chat import post
from test_task_domain import authenticate, create_organization, create_project

from app.models import OrganizationMember, ProjectMember, Task
from app.repositories.task_access import TaskAccessRepository
from app.services.domain import DomainService


@pytest.fixture
async def matrix(client, db_session):
    admin = await authenticate(client, uuid4())
    org_a = await create_organization(client, admin, "A")
    org_b = await create_organization(client, admin, "B")
    projects = [await create_project(client, admin, org_a["id"], name) for name in ("A1", "A2")]
    projects.append(await create_project(client, admin, org_b["id"], "B1"))
    tasks = []
    for project in projects:
        status = (
            await client.get(f"/api/projects/{project['id']}/statuses", headers=admin)
        ).json()[0]
        response = await client.post(
            f"/api/projects/{project['id']}/tasks",
            headers=admin,
            json={"title": project["name"], "status_id": status["id"]},
        )
        assert response.status_code == 201
        tasks.append(response.json())
    actors = {}
    for role in ("sa", "om", "pm", "employee", "org_only", "outsider", "revoked", "archived"):
        headers = await authenticate(client, uuid4())
        uid = authenticated_id(headers)
        actors[role] = headers
        from app.models import User

        if role == "sa":
            (await db_session.get(User, uid)).is_system_admin = True
        elif role != "outsider":
            db_session.add(
                OrganizationMember(
                    organization_id=UUID(org_a["id"]),
                    user_id=uid,
                    role="manager" if role == "om" else "member",
                    state="active",
                )
            )
            if role in {"pm", "employee", "revoked", "archived"}:
                db_session.add(
                    ProjectMember(
                        project_id=UUID(projects[0]["id"]),
                        user_id=uid,
                        role="manager" if role in {"pm", "archived"} else "member",
                        state=role if role in {"revoked", "archived"} else "active",
                    )
                )
    await db_session.commit()
    return actors, projects, tasks


async def test_role_resource_matrix(client, db_session, matrix, attachment_storage):
    actors, projects, tasks = matrix
    from app.models import Attachment
    from app.services.attachment_maintenance import AttachmentMaintenance

    downloads = []
    for task in tasks:
        uploaded = await post(client, task, actors["sa"], files=[("files", ("note.txt", b"safe"))])
        attachment = uploaded.json()["attachments"][0]
        assert attachment["state"] == "pending"
        url = f"/api/attachments/{attachment['id']}/content"
        assert (await client.get(url, headers=actors["sa"])).status_code == 404
        row = await db_session.get(Attachment, UUID(attachment["id"]))
        await AttachmentMaintenance(db_session, attachment_storage).review(
            row.id, row.sha256, "ready"
        )
        downloads.append(url)
    reads = {
        "sa": {0, 1, 2},
        "om": {0, 1, 2},
        "pm": {0, 1},
        "employee": {0},
        "org_only": set(),
        "outsider": set(),
        "revoked": set(),
        "archived": set(),
    }
    writes = {"sa": {0, 1, 2}, "om": {0, 1}, "pm": {0}, "employee": {0}}
    for role, headers in actors.items():
        for index, (project, task) in enumerate(zip(projects, tasks, strict=True)):
            readable = index in reads[role]
            assert (await client.get(downloads[index], headers=headers)).status_code == (
                200 if readable else 404
            )
            for path in (
                f"/tasks/{task['id']}",
                f"/tasks/{task['id']}/history",
                f"/tasks/{task['id']}/comments",
                f"/tasks/{task['id']}/watchers",
                f"/projects/{project['id']}/board",
                f"/projects/{project['id']}/statuses",
            ):
                response = await client.get("/api" + path, headers=headers)
                assert response.status_code == (200 if readable else 404), (
                    role,
                    path,
                    response.text,
                )
            assert (
                authenticated_id(headers)
                in await TaskAccessRepository(db_session).reader_ids(UUID(project["id"]))
            ) == readable
            comment = await post(client, task, headers)
            assert comment.status_code == (201 if readable else 404), (role, comment.text)
            changed = await client.patch(
                f"/api/tasks/{task['id']}",
                headers=headers,
                json={
                    "title": role,
                    "story_points": 8,
                    "priority": "major",
                    "due_date": "2030-01-01",
                },
            )
            assert changed.status_code == (
                200 if index in writes.get(role, set()) else 403 if readable else 404
            ), (role, changed.text)
            if readable:
                result = (await client.get(f"/api/tasks/{task['id']}", headers=headers)).json()
                assert result["capabilities"]["edit"] == (index in writes.get(role, set()))
                assert result["capabilities"]["comment"]
    task = await db_session.get(Task, UUID(tasks[0]["id"]))
    assert not await DomainService(db_session).can_archive_task(
        authenticated_id(actors["employee"]), task
    )
    for field in ("created_by", "reporter_id", "assignee_id"):
        old = getattr(task, field)
        setattr(task, field, authenticated_id(actors["employee"]))
        assert await DomainService(db_session).can_archive_task(
            authenticated_id(actors["employee"]), task
        )
        setattr(task, field, old)


async def test_candidates_watchers_revocation_and_notifications(client, db_session, matrix):
    actors, projects, tasks = matrix
    task, project = tasks[0], projects[0]
    employee = authenticated_id(actors["employee"])
    om = authenticated_id(actors["om"])
    outsider = authenticated_id(actors["outsider"])
    base = f"/api/tasks/{task['id']}"
    mentions = (
        await client.get(base + "/participants?kind=mention", headers=actors["employee"])
    ).json()
    ids = {row["id"] for row in mentions["items"]}
    assert str(om) in ids and str(outsider) not in ids
    assignees = (
        await client.get(base + "/participants?kind=assignee", headers=actors["employee"])
    ).json()
    assert str(om) not in {row["id"] for row in assignees["items"]}
    assert str(employee) in {row["id"] for row in assignees["items"]}
    page = (
        await client.get(base + "/participants?kind=mention&limit=1", headers=actors["employee"])
    ).json()
    assert page["next_cursor"]
    assert (
        await client.get(
            base + "/participants",
            headers=actors["employee"],
            params={"kind": "assignee", "cursor": page["next_cursor"]},
        )
    ).status_code == 422
    assert (
        await client.post(base + "/watchers", headers=actors["sa"], json={"user_id": str(om)})
    ).status_code == 200
    assert (
        await db_session.get(ProjectMember, {"project_id": UUID(project["id"]), "user_id": om})
        is None
    )
    assert (
        await client.post(base + "/watchers", headers=actors["sa"], json={"user_id": str(outsider)})
    ).status_code == 422
    # An ordinary member can replace every field even on another author's task.
    assert (
        await client.patch(
            base,
            headers=actors["employee"],
            json={"assignee_id": str(employee), "reporter_id": str(employee)},
        )
    ).status_code == 200
    assert (
        await client.patch(base, headers=actors["employee"], json={"assignee_id": str(om)})
    ).status_code == 422
    assert (
        await post(client, task, actors["sa"], mentions=[str(om), str(employee)])
    ).status_code == 201
    notification = (await client.get("/api/notifications", headers=actors["employee"])).json()[0]
    member = await db_session.get(
        ProjectMember, {"project_id": UUID(project["id"]), "user_id": employee}
    )
    member.state = "revoked"
    await db_session.commit()
    assert (await post(client, task, actors["sa"], mentions=[str(employee)])).status_code == 422
    assert (await client.get("/api/notifications", headers=actors["employee"])).json() == []
    assert (await client.get("/api/notifications/unread-count", headers=actors["employee"])).json()[
        "count"
    ] == 0
    assert (
        await client.post(
            f"/api/notifications/{notification['id']}/open", headers=actors["employee"]
        )
    ).status_code == 404
    assert (await client.get(base, headers=actors["employee"])).status_code == 404
    await db_session.refresh(task_row := await db_session.get(Task, UUID(task["id"])))
    assert task_row.assignee_id == employee
    assert (
        await client.patch(
            base, headers=actors["sa"], json={"title": "Preserved", "assignee_id": str(employee)}
        )
    ).status_code == 200


async def test_search_links_and_creation_do_not_bypass_scopes(client, db_session, matrix):
    actors, projects, tasks = matrix
    employee = actors["employee"]
    org = projects[0]["organization_id"]
    listed = (await client.get(f"/api/organizations/{org}/projects", headers=employee)).json()
    assert [row["id"] for row in listed] == [projects[0]["id"]]
    found = await client.get(
        f"/api/organizations/{org}/tasks/search", params={"slug": "A"}, headers=employee
    )
    assert found.status_code == 200, found.text
    assert {row["id"] for row in found.json()["items"]} == {tasks[0]["id"]}
    link = await client.post(
        f"/api/tasks/{tasks[0]['id']}/links",
        headers=actors["sa"],
        json={"target_task_id": tasks[1]["id"], "relation_type": "related"},
    )
    assert link.status_code == 201, link.text
    history = (await client.get(f"/api/tasks/{tasks[0]['id']}/history", headers=employee)).json()
    assert history["entries"] == []
    assert (await client.get(f"/api/tasks/{tasks[0]['id']}/links", headers=employee)).json() == []
    assert (
        await client.delete(
            f"/api/tasks/{tasks[0]['id']}/links/{link.json()['id']}", headers=employee
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/tasks/{tasks[0]['id']}/links",
            headers=employee,
            json={"target_task_id": tasks[1]["id"], "relation_type": "blocks"},
        )
    ).status_code == 404
    payload = {"title": "Explicit reporter", "status_id": tasks[0]["status_id"]}
    create_path = f"/api/projects/{projects[0]['id']}/tasks"
    assert (await client.post(create_path, headers=actors["sa"], json=payload)).status_code == 422
    payload["reporter_id"] = str(authenticated_id(employee))
    assert (await client.post(create_path, headers=actors["sa"], json=payload)).status_code == 201
    assert (
        await client.patch(
            f"/api/tasks/{tasks[0]['id']}",
            headers=employee,
            json={"status_id": tasks[1]["status_id"]},
        )
    ).status_code == 422


async def test_deadline_retained_assignment_requires_current_reading(client, db_session, matrix):
    from datetime import date

    from app.services.deadlines import DeadlineService

    actors, projects, tasks = matrix
    manager_id = authenticated_id(actors["om"])
    task = await db_session.get(Task, UUID(tasks[2]["id"]))
    # A historical assignment may remain after membership removal. The independent
    # global OM read grant still qualifies this recipient; assignment alone does not.
    task.assignee_id = manager_id
    task.due_date = date(2030, 1, 1)
    await db_session.commit()
    assert await DeadlineService(db_session).process_due(date(2030, 1, 1)) == 1
    assert len((await client.get("/api/notifications", headers=actors["om"])).json()) == 1
    role = await db_session.get(
        OrganizationMember,
        {
            "organization_id": UUID(projects[0]["organization_id"]),
            "user_id": manager_id,
        },
    )
    role.state = "revoked"
    task.due_date = date(2030, 1, 2)
    await db_session.commit()
    assert await DeadlineService(db_session).process_due(date(2030, 1, 2)) == 0
    assert (await client.get("/api/notifications", headers=actors["om"])).json() == []
