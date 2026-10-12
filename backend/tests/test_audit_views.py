import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from auth_helpers import authenticated_id
from test_archive_lifecycle import lifecycle
from test_task_access import matrix  # noqa: F401
from test_task_domain import authenticate

from app.models import OrganizationMember, ProjectMember, User
from app.schemas.administrative_audit import AdministrativeAuditWrite, AuditChange
from app.services.administrative_audit import AdministrativeAuditService


async def test_user_pages_binding_identity_and_live_insertion(client, db_session):
    owner = await authenticate(client, uuid4())
    outsider = await authenticate(client, uuid4())
    uid = authenticated_id(owner)
    writer = AdministrativeAuditService(db_session)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(1, 42):
        row = writer.record(
            AdministrativeAuditWrite(
                actor_id=uid,
                entity_type="user",
                entity_id=uid,
                action="profile_updated",
                changes=(
                    AuditChange(field="first_name", old="Old", new="New"),
                    AuditChange(field="last_name", old="Before", new="After"),
                ),
            )
        )
        row.id, row.occurred_at = UUID(int=i), timestamp
    await db_session.commit()
    url = f"/api/users/{uid}/audit"
    first = await client.get(url, headers=owner)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["page_size"] == 20
    assert [UUID(e["id"]).int for e in body["items"]] == list(range(41, 21, -1))
    assert len(body["items"][0]["changes"]) == 2
    assert body["items"][0]["actor"]["display_name"] == "Test User"
    row = writer.record(
        AdministrativeAuditWrite(
            actor_kind="bootstrap",
            actor_id=None,
            entity_type="user",
            entity_id=uid,
            action="system_role_changed",
            changes=(AuditChange(field="is_system_admin", old=False, new=True),),
        )
    )
    row.occurred_at = timestamp + timedelta(seconds=1)
    await db_session.commit()
    second = (await client.get(url, headers=owner, params={"cursor": body["next_cursor"]})).json()
    assert [UUID(e["id"]).int for e in second["items"]] == list(range(21, 1, -1))
    third = (await client.get(url, headers=owner, params={"cursor": second["next_cursor"]})).json()
    assert len(third["items"]) == 1 and third["next_cursor"] is None
    end_cursor = base64.urlsafe_b64encode(
        json.dumps(["audit", "user", str(uid), timestamp.isoformat(), str(UUID(int=1))]).encode()
    ).decode()
    empty = await client.get(url, headers=owner, params={"cursor": end_cursor})
    assert empty.json() == {"items": [], "next_cursor": None, "page_size": 20}
    assert (await client.get(f"/api/users/{uid}", headers=owner)).json()["capabilities"][
        "view_audit"
    ]
    assert not (await client.get(f"/api/users/{uid}", headers=outsider)).json()["capabilities"][
        "view_audit"
    ]
    assert (await client.get(url, headers=owner)).json()["items"][0]["actor"] == {
        "kind": "bootstrap",
        "id": None,
        "display_name": "System bootstrap",
    }
    assert (await client.get(url, headers=outsider)).status_code == 403
    assert (await client.get(url)).status_code == 401
    assert (await client.get(f"/api/users/{uuid4()}/audit", headers=owner)).status_code == 404
    other_url = f"/api/users/{authenticated_id(outsider)}/audit"
    assert (await client.get(other_url, headers=outsider)).json()["items"] == []
    assert (
        await client.get(other_url, headers=outsider, params={"cursor": body["next_cursor"]})
    ).status_code == 422
    for params in (
        {"limit": 20},
        {"page_size": 20},
        {"cursor": "broken"},
        {"cursor": ""},
        {"filter": "all"},
    ):
        assert (await client.get(url, headers=owner, params=params)).status_code == 422
    user = await db_session.get(User, uid)
    user.must_change_password = True
    await db_session.commit()
    assert (await client.get(url, headers=owner)).status_code == 403
    user.is_active = False
    await db_session.commit()
    assert (await client.get(url, headers=owner)).status_code == 401


async def test_resource_access_archive_cascade_and_revoked_read(client, db_session, matrix):  # noqa: F811
    actors, projects, tasks = matrix
    project, task = projects[0], tasks[0]
    org_id = project["organization_id"]
    for scope, identifier in (
        ("organizations", org_id),
        ("projects", project["id"]),
        ("tasks", task["id"]),
    ):
        url = f"/api/{scope}/{identifier}/audit"
        assert (await client.get(url, headers=actors["employee"])).status_code == 200
        assert (await client.get(url, headers=actors["outsider"])).status_code == 404
        assert (
            await client.get(f"/api/{scope}/{uuid4()}/audit", headers=actors["sa"])
        ).status_code == 404
    assert (await lifecycle(client, actors["sa"], "organization", org_id)).status_code == 200
    operations = []
    for scope, identifier in (
        ("organizations", org_id),
        ("projects", project["id"]),
        ("tasks", task["id"]),
    ):
        url = f"/api/{scope}/{identifier}/audit"
        response = await client.get(url, headers=actors["employee"])
        assert response.status_code == 200, response.text
        archived = [e for e in response.json()["items"] if e["action"] == "archived"]
        assert len(archived) == 1
        operations.append(archived[0]["operation_id"])
    assert len(set(operations)) == 1
    assert (await lifecycle(client, actors["sa"], "organization", org_id)).status_code == 200
    member = await db_session.get(
        OrganizationMember, (UUID(org_id), authenticated_id(actors["employee"]))
    )
    member.state = "revoked"
    project_member = await db_session.get(
        ProjectMember, (UUID(project["id"]), authenticated_id(actors["employee"]))
    )
    project_member.state = "revoked"
    await db_session.commit()
    for scope, identifier in (
        ("organizations", org_id),
        ("projects", project["id"]),
        ("tasks", task["id"]),
    ):
        assert (
            await client.get(f"/api/{scope}/{identifier}/audit", headers=actors["employee"])
        ).status_code == 404
    target = authenticated_id(actors["employee"])
    assert (await client.get(f"/api/users/{target}/audit", headers=actors["sa"])).status_code == 200
    assert (await client.get(f"/api/users/{target}/audit", headers=actors["om"])).status_code == 403


async def test_membership_events_are_paired_without_user_audit_leak(client, matrix):  # noqa: F811
    actors, projects, _ = matrix
    target = authenticated_id(actors["employee"])
    project = projects[0]
    url = f"/api/projects/{project['id']}/members/{target}"
    assert (
        await client.put(url, headers=actors["sa"], json={"role": "manager"})
    ).status_code == 200
    resource = (
        await client.get(f"/api/projects/{project['id']}/audit", headers=actors["employee"])
    ).json()
    user = (await client.get(f"/api/users/{target}/audit", headers=actors["employee"])).json()
    a = [e for e in resource["items"] if e["action"] == "member_role_changed"]
    b = [e for e in user["items"] if e["action"] == "member_role_changed"]
    assert len(a) == len(b) == 1
    assert a[0]["operation_id"] == b[0]["operation_id"]
    assert a[0]["subject_user_id"] == b[0]["subject_user_id"] == str(target)
    assert all(e["entity"]["type"] == "project" for e in resource["items"])


async def test_page_rechecks_project_access_and_missing_actor_falls_back_to_id(
    client,
    db_session,
    matrix,  # noqa: F811
):
    actors, projects, _ = matrix
    project_id = UUID(projects[0]["id"])
    missing_actor = uuid4()
    audit = AdministrativeAuditService(db_session)
    for _ in range(21):
        audit.record(
            AdministrativeAuditWrite(
                actor_id=missing_actor,
                entity_type="project",
                entity_id=project_id,
                action="updated",
                changes=(AuditChange(field="name", old="Old", new="New"),),
            )
        )
    await db_session.commit()
    url = f"/api/projects/{project_id}/audit"
    page = (await client.get(url, headers=actors["employee"])).json()
    assert page["items"][0]["actor"]["display_name"] == str(missing_actor)
    assert page["next_cursor"]
    member = await db_session.get(ProjectMember, (project_id, authenticated_id(actors["employee"])))
    member.state = "revoked"
    await db_session.commit()
    assert (
        await client.get(url, headers=actors["employee"], params={"cursor": page["next_cursor"]})
    ).status_code == 404
    assert (
        await client.get(url, headers=actors["sa"], params={"cursor": page["next_cursor"]})
    ).status_code == 200
    assert (
        await client.get(
            f"/api/organizations/{projects[0]['organization_id']}/audit",
            headers=actors["sa"],
            params={"cursor": page["next_cursor"]},
        )
    ).status_code == 422
