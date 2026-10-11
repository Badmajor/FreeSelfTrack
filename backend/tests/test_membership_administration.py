from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from auth_helpers import authenticated_id, set_system_admin
from sqlalchemy import func, select
from test_task_domain import authenticate, create_organization, create_project

from app.models import OrganizationMember, Project, ProjectMember, TaskHistory
from app.models.administrative_audit import AdministrativeAuditEvent
from app.services.administrative_audit import AdministrativeAuditService


async def context(client):
    admin = await authenticate(client, uuid4())
    manager = await authenticate(client, uuid4())
    employee = await authenticate(client, uuid4())
    org = await create_organization(client, admin, "First")
    await set_system_admin(admin)
    project = await create_project(client, admin, org["id"], "Project")
    return admin, manager, employee, org, project


async def put(client, headers, scope, parent, target, role="member"):
    return await client.put(
        f"/api/{scope}s/{parent}/members/{authenticated_id(target)}",
        headers=headers,
        json={"role": role},
    )


async def test_roles_readd_descriptions_and_noop_audit(client, db_session):
    admin, manager, employee, org, project = await context(client)
    assert (
        await put(client, admin, "organization", org["id"], manager, "manager")
    ).status_code == 200
    assert (await put(client, admin, "organization", org["id"], employee)).status_code == 200
    assert (
        await put(client, manager, "project", project["id"], employee, "manager")
    ).status_code == 200
    assert (await put(client, manager, "project", project["id"], employee)).status_code == 200
    # Last manager demotion retains ordinary participation.
    response = await put(client, admin, "organization", org["id"], manager)
    assert response.json()["role"] == "member"
    assert response.json()["state"] == "active"
    before = await db_session.scalar(select(func.count()).select_from(AdministrativeAuditEvent))
    assert (await put(client, admin, "organization", org["id"], manager)).status_code == 200
    assert (
        await db_session.scalar(select(func.count()).select_from(AdministrativeAuditEvent))
        == before
    )
    url = f"/api/projects/{project['id']}/members/{authenticated_id(employee)}"
    for _ in range(2):
        assert (await client.delete(url, headers=admin)).status_code == 204
    assert (await put(client, admin, "project", project["id"], employee)).status_code == 200
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .where(
                ProjectMember.project_id == UUID(project["id"]),
                ProjectMember.user_id == authenticated_id(employee),
            )
        )
        == 1
    )
    for scope, identifier in (("organizations", org["id"]), ("projects", project["id"])):
        url = f"/api/{scope}/{identifier}"
        saved = await client.patch(
            url, headers=admin, json={"name": " Renamed ", "description": "Details"}
        )
        assert saved.status_code == 200 and saved.json()["name"] == "Renamed"
        assert saved.json()["description"] == "Details"
        assert (await client.patch(url, headers=admin, json={"description": None})).json()[
            "description"
        ] is None
        for body in ({"name": None}, {"name": " "}, {"owner_id": str(uuid4())}):
            assert (await client.patch(url, headers=admin, json=body)).status_code == 422


async def test_global_hierarchy_scope_and_manager_assignment(client, db_session):
    admin, manager, employee, org, project = await context(client)
    other_org = await create_organization(client, admin, "Other")
    await set_system_admin(admin)
    for target in (manager, employee):
        assert (await put(client, admin, "organization", org["id"], target)).status_code == 200
    assert (
        await put(client, admin, "organization", org["id"], manager, "manager")
    ).status_code == 200
    assert (
        await put(client, admin, "organization", other_org["id"], employee, "manager")
    ).status_code == 200
    for scope, identifier in (("organization", org["id"]), ("project", project["id"])):
        response = await put(client, manager, scope, identifier, employee)
        assert response.status_code == 403 and response.json()["code"] == "membership_hierarchy"
        response = await client.delete(
            f"/api/{scope}s/{identifier}/members/{authenticated_id(employee)}", headers=manager
        )
        assert response.status_code == 403
    assert (await put(client, manager, "organization", other_org["id"], admin)).status_code == 403
    assert (await put(client, manager, "organization", org["id"], manager)).status_code == 403
    # Archived role does not raise the target's level.
    member = await db_session.get(
        OrganizationMember, (UUID(other_org["id"]), authenticated_id(employee))
    )
    member.state = "archived"
    await db_session.commit()
    assert (await put(client, manager, "project", project["id"], employee)).status_code == 200
    assert (
        await put(client, manager, "organization", org["id"], employee, "manager")
    ).status_code == 403
    assert (
        await put(client, admin, "project", project["id"], manager, "manager")
    ).status_code == 200
    # OM in this org still has manager-management rights; test PM with a separate account.
    pm = await authenticate(client, uuid4())
    assert (await put(client, admin, "organization", org["id"], pm)).status_code == 200
    assert (await put(client, admin, "project", project["id"], pm, "manager")).status_code == 200
    assert (await put(client, pm, "project", project["id"], employee, "manager")).status_code == 403
    assert (await put(client, pm, "project", project["id"], employee)).status_code == 200
    outsider = await authenticate(client, uuid4())
    assert (await put(client, pm, "project", project["id"], outsider)).status_code == 422
    assert (
        await client.post(
            f"/api/organizations/{org['id']}/users",
            headers=pm,
            json={"email": "new@example.com", "first_name": "New", "last_name": "User"},
        )
    ).status_code == 403


async def test_create_managers_atomicity_and_audit_failure(client, db_session, monkeypatch):
    admin, manager, employee, org, _ = await context(client)
    for target in (manager, employee):
        assert (await put(client, admin, "organization", org["id"], target)).status_code == 200
    body = {
        "organization_id": org["id"],
        "name": "New",
        "description": "Description",
        "manager_ids": [str(authenticated_id(manager)), str(authenticated_id(employee))],
    }
    response = await client.post("/api/projects", headers=admin, json=body)
    assert response.status_code == 201
    identifier = UUID(response.json()["id"])
    members = list(
        await db_session.scalars(
            select(ProjectMember).where(ProjectMember.project_id == identifier)
        )
    )
    assert len(members) == 2 and all(m.role == "manager" for m in members)
    assert authenticated_id(admin) not in {m.user_id for m in members}
    before = await db_session.scalar(select(func.count()).select_from(Project))
    for ids, status in (([str(uuid4())], 422), ([str(authenticated_id(manager))] * 2, 422)):
        assert (
            await client.post("/api/projects", headers=admin, json={**body, "manager_ids": ids})
        ).status_code == status
    assert await db_session.scalar(select(func.count()).select_from(Project)) == before

    def fail(*args, **kwargs):
        raise RuntimeError("audit failure")

    monkeypatch.setattr(AdministrativeAuditService, "record", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        await put(client, admin, "project", str(identifier), manager)
    db_session.expire_all()
    assert (
        await db_session.get(ProjectMember, (identifier, authenticated_id(manager)))
    ).role == "manager"


async def test_assignee_context_readd_preserves_ids_history_and_cascade(client, db_session):
    admin, _, employee, org, project = await context(client)
    await put(client, admin, "organization", org["id"], employee)
    await put(client, admin, "project", project["id"], employee)
    statuses = (await client.get(f"/api/projects/{project['id']}/statuses", headers=admin)).json()
    created = await client.post(
        f"/api/projects/{project['id']}/tasks",
        headers=admin,
        json={
            "title": "Keep assignment",
            "status_id": statuses[0]["id"],
            "assignee_id": str(authenticated_id(employee)),
        },
    )
    assert created.status_code == 201
    task = created.json()
    before = await db_session.scalar(select(func.count()).select_from(TaskHistory))
    for scope, identifier, reason in (
        ("project", project["id"], "project_membership_revoked"),
        ("organization", org["id"], "organization_membership_revoked"),
    ):
        assert (
            await client.delete(
                f"/api/{scope}s/{identifier}/members/{authenticated_id(employee)}", headers=admin
            )
        ).status_code == 204
        response = (await client.get(f"/api/tasks/{task['id']}", headers=admin)).json()
        assert reason in response["assignee"]["unavailable_reasons"]
        assert response["assignee"]["is_active"] is True
        for field in ("created_by", "reporter_id", "assignee_id"):
            assert response[field] == task[field]
        await put(client, admin, "organization", org["id"], employee)
        await put(client, admin, "project", project["id"], employee)
        response = (await client.get(f"/api/tasks/{task['id']}", headers=admin)).json()
        assert response["assignee"]["unavailable_reasons"] == []
    assert await db_session.scalar(select(func.count()).select_from(TaskHistory)) == before
    member = await db_session.get(ProjectMember, (UUID(project["id"]), authenticated_id(employee)))
    member.state = "archived"
    await db_session.commit()
    assert (await client.get(f"/api/tasks/{task['id']}", headers=admin)).json()["assignee"][
        "unavailable_reasons"
    ] == []


async def test_pages_validation_archive_and_removed_email_api(client, db_session):
    admin, manager, employee, org, project = await context(client)
    await put(client, admin, "organization", org["id"], manager)
    await put(client, admin, "organization", org["id"], employee)
    url = f"/api/organizations/{org['id']}/members"
    response = await client.get(url, headers=admin, params={"limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1 and body["next_cursor"]
    assert "email" not in body["items"][0]["user"]
    second = await client.get(
        url, headers=admin, params={"cursor": body["next_cursor"], "limit": 1}
    )
    assert second.json()["items"][0] != body["items"][0]
    assert (
        await client.get(
            url, headers=admin, params={"cursor": body["next_cursor"], "state": "archived"}
        )
    ).status_code == 422
    assert (await client.get(url)).status_code == 401
    assert (
        await client.post(url, headers=admin, json={"email": "old@example.com"})
    ).status_code == 404
    target_url = f"{url}/{authenticated_id(employee)}"
    assert (
        await client.put(target_url, headers=admin, json={"role": "member", "state": "active"})
    ).status_code == 422
    assert (await client.delete(f"{url}/{uuid4()}", headers=admin)).status_code == 204
    parent = await db_session.get(Project, UUID(project["id"]))
    parent.deleted_at = datetime.now(UTC)
    await db_session.commit()
    assert (await put(client, admin, "project", project["id"], employee)).status_code == 409


async def test_no_implicit_membership_and_removed_assignee_other_field_patch(client, db_session):
    admin, _, employee, org, project = await context(client)
    await put(client, admin, "organization", org["id"], employee)
    status = (await client.get(f"/api/projects/{project['id']}/statuses", headers=admin)).json()[0]
    url = f"/api/projects/{project['id']}/tasks"
    body = {"title": "No autojoin", "status_id": status["id"]}
    target = str(authenticated_id(employee))
    for field in ("reporter_id", "assignee_id"):
        assert (
            await client.post(url, headers=admin, json={**body, field: target})
        ).status_code == 422
    task = (await client.post(url, headers=admin, json=body)).json()
    url = f"/api/tasks/{task['id']}"
    assert (
        await client.post(f"{url}/watchers", headers=admin, json={"user_id": target})
    ).status_code == 422
    assert await db_session.get(ProjectMember, (UUID(project["id"]), UUID(target))) is None
    await put(client, admin, "project", project["id"], employee)
    assert (await client.patch(url, headers=admin, json={"assignee_id": target})).status_code == 200
    await client.delete(f"/api/projects/{project['id']}/members/{target}", headers=admin)
    changed = await client.patch(url, headers=admin, json={"title": "Retained assignment"})
    assert changed.status_code == 200 and changed.json()["assignee_id"] == target


async def test_project_manager_peers_elsewhere_and_workflow_guards(client, db_session):
    admin, pm, employee, org, project = await context(client)
    other = await create_project(client, admin, org["id"], "Other")
    for target in (pm, employee):
        await put(client, admin, "organization", org["id"], target)
        await put(client, admin, "project", project["id"], target)
    await put(client, admin, "project", project["id"], pm, "manager")
    await put(client, admin, "project", other["id"], employee, "manager")
    for role in ("member", "manager"):
        response = await put(client, pm, "project", project["id"], employee, role)
        assert response.status_code == 403 and response.json()["code"] == "membership_hierarchy"
    assert (
        await client.delete(
            f"/api/projects/{project['id']}/members/{authenticated_id(employee)}", headers=pm
        )
    ).status_code == 403
    # PM can configure its own workflow, independently of manager-assignment permission.
    assert (
        await client.post(
            f"/api/projects/{project['id']}/statuses", headers=pm, json={"name": "Review"}
        )
    ).status_code == 201
    assert (
        await client.post(
            f"/api/projects/{other['id']}/statuses", headers=pm, json={"name": "Forbidden"}
        )
    ).status_code == 404
    await put(client, admin, "project", other["id"], employee)
    assert (
        await client.post(
            f"/api/projects/{project['id']}/statuses", headers=employee, json={"name": "Forbidden"}
        )
    ).status_code == 403
    # Organization-only membership does not grant this project's directory.
    await client.delete(
        f"/api/projects/{project['id']}/members/{authenticated_id(employee)}", headers=admin
    )
    assert (
        await client.get(f"/api/projects/{project['id']}/members", headers=employee)
    ).status_code == 404


async def test_created_managers_share_one_audit_operation(client, db_session):
    admin, manager, employee, org, _ = await context(client)
    for target in (manager, employee):
        await put(client, admin, "organization", org["id"], target)
    response = await client.post(
        "/api/projects",
        headers=admin,
        json={
            "organization_id": org["id"],
            "name": "Multiple managers",
            "manager_ids": [str(authenticated_id(manager)), str(authenticated_id(employee))],
        },
    )
    assert response.status_code == 201
    created = await db_session.scalar(
        select(AdministrativeAuditEvent).where(
            AdministrativeAuditEvent.entity_id == UUID(response.json()["id"]),
            AdministrativeAuditEvent.action == "created",
        )
    )
    events = list(
        await db_session.scalars(
            select(AdministrativeAuditEvent).where(
                AdministrativeAuditEvent.operation_id == created.operation_id,
            )
        )
    )
    assert len(events) == 5
    assert sum(event.entity_type == "user" for event in events) == 2


async def test_remote_om_does_not_expand_local_pm_membership_authority(client, db_session):
    admin, actor, target, org, project = await context(client)
    other_org = await create_organization(client, admin, "Remote authority")
    await set_system_admin(admin)
    for user in (actor, target):
        await put(client, admin, "organization", org["id"], user)
        await put(client, admin, "project", project["id"], user, "manager")
    await put(client, admin, "organization", other_org["id"], actor, "manager")
    # Global OM > PM is not enough: in this scope the actor is only PM.
    for role in ("member", "manager"):
        response = await put(client, actor, "project", project["id"], target, role)
        assert response.status_code == 403
    response = await client.delete(
        f"/api/projects/{project['id']}/members/{authenticated_id(target)}", headers=actor
    )
    assert response.status_code == 403
    member = await db_session.get(ProjectMember, (UUID(project["id"]), authenticated_id(target)))
    assert member.role == "manager" and member.state == "active"
