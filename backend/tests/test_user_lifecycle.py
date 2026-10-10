from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from auth_helpers import seed_account, set_system_admin
from sqlalchemy import select
from test_task_domain import authenticate, create_organization, create_project

from app.main import app
from app.models import OrganizationMember, ProjectMember, TaskHistory, User
from app.models.administrative_audit import AdministrativeAuditEvent
from app.models.auth_session import PasswordReset
from app.models.registration import PendingRegistration
from app.services.auth import password_hash
from app.services.sessions import reset_token, token_digest
from app.services.verification import create_verification_token

PASSWORD = "correct horse battery staple"


async def administrator(client):
    headers = await authenticate(client, uuid4())
    await set_system_admin(headers)
    return headers


async def create(client, headers, email="created@example.com", path="/api/users"):
    return await client.post(
        path,
        headers=headers,
        json={
            "email": email,
            "first_name": "New",
            "last_name": "User",
        },
    )


async def login(client, email, password):
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


async def test_create_temporary_repeat_login_change_and_no_secret_readback(client, db_session):
    admin = await administrator(client)
    response = await create(client, admin)
    assert response.status_code == 201, response.text
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    temporary = data["temporary_password"]
    assert data["user"]["must_change_password"]
    row = await db_session.get(User, UUID(data["user"]["id"]))
    assert row.password_hash != temporary and password_hash.verify(temporary, row.password_hash)
    assert await db_session.scalar(select(PendingRegistration)) is None
    assert await db_session.scalar(select(PasswordReset)) is None
    assert (await create(client, admin)).status_code == 409
    first = await login(client, row.email, temporary)
    second = await login(client, row.email, temporary)
    assert (await client.post("/api/auth/refresh")).json()["user"]["must_change_password"]
    assert temporary not in (await client.get("/api/users", headers=admin)).text
    result = await client.post(
        "/api/auth/password/change",
        headers=second,
        json={"current_password": temporary, "new_password": PASSWORD},
    )
    assert result.status_code == 204
    for headers in (first, second):
        assert (await client.get("/api/users", headers=headers)).status_code == 401
    normal = await login(client, row.email, PASSWORD)
    assert (await client.get("/api/users", headers=normal)).status_code == 200
    assert (
        await client.post("/api/auth/login", json={"email": row.email, "password": temporary})
    ).status_code == 401
    events = (await db_session.scalars(select(AdministrativeAuditEvent))).all()
    assert [e.action for e in events] == ["user_created"]
    assert temporary not in str([e.changes for e in events])


async def test_restricted_session_rejects_every_protected_route(client):
    admin = await administrator(client)
    created = (await create(client, admin)).json()
    restricted = await login(client, "created@example.com", created["temporary_password"])
    # Exercise all registered domain routes, including file/chat/profile endpoints.
    from fastapi.routing import APIRoute

    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        if route.path.startswith("/api/auth/"):
            continue
        path = route.path
        for parameter in route.param_convertors:
            path = path.replace("{" + parameter + "}", str(uuid4()))
        for method in route.methods:
            response = await client.request(method, path, headers=restricted)
            assert response.status_code == 403, (method, path, response.text)
            assert response.json()["code"] == "password_change_required"
    assert (
        await client.delete("/api/auth/sessions/current", headers=restricted)
    ).status_code == 204


async def test_global_manager_block_preserves_assignment_and_unblock_does_not_restore(
    client, db_session
):
    manager = await authenticate(client, uuid4())
    other = await authenticate(client, uuid4())
    org = await create_organization(client, manager, "First")
    other_org = await create_organization(client, other, "Other")
    project = await create_project(client, other, other_org["id"], "Work")
    from auth_helpers import authenticated_id

    target = authenticated_id(other)
    statuses = (await client.get(f"/api/projects/{project['id']}/statuses", headers=other)).json()
    task = (
        await client.post(
            f"/api/projects/{project['id']}/tasks",
            headers=other,
            json={"title": "Retained", "status_id": statuses[0]["id"], "assignee_id": str(target)},
        )
    ).json()
    before = list(await db_session.scalars(select(TaskHistory.id)))
    cookie = client.cookies.get("__Secure-fst-refresh")
    blocked = await client.post(
        f"/api/users/{target}/block", headers=manager, json={"confirm": True}
    )
    assert blocked.status_code == 200, blocked.text
    assert not blocked.json()["is_active"]
    assert (await client.get("/api/users", headers=other)).status_code == 401
    assert (
        await client.post("/api/auth/refresh", headers={"Cookie": f"__Secure-fst-refresh={cookie}"})
    ).status_code == 401
    for model in (OrganizationMember, ProjectMember):
        memberships = (await db_session.scalars(select(model).where(model.user_id == target))).all()
        assert memberships and all(m.state == "revoked" and m.role == "member" for m in memberships)
    await set_system_admin(manager)
    saved = (await client.get(f"/api/tasks/{task['id']}", headers=manager)).json()
    for key in ("assignee_id", "created_by", "reporter_id"):
        assert saved[key] == task[key]
    assert saved["assignee"]["is_active"] is False
    assert list(await db_session.scalars(select(TaskHistory.id))) == before
    for _ in range(2):
        assert (
            await client.post(f"/api/users/{target}/unblock", headers=manager)
        ).status_code == 200
    rows = (
        await db_session.scalars(
            select(AdministrativeAuditEvent).where(
                AdministrativeAuditEvent.entity_id == target,
                AdministrativeAuditEvent.action.in_(["user_blocked", "user_unblocked"]),
            )
        )
    ).all()
    assert len(rows) == 2
    restored = await login(client, (await db_session.get(User, target)).email, PASSWORD)
    assert (await client.get(f"/api/tasks/{task['id']}", headers=restored)).status_code == 404
    assert org["id"] != other_org["id"]


async def test_roles_create_atomic_membership_reset_and_admin_protection(client, db_session):
    manager = await authenticate(client, uuid4())
    org = await create_organization(client, manager, "Managed")
    assert (await create(client, manager)).status_code == 403
    assert (
        await create(client, manager, path=f"/api/organizations/{uuid4()}/users")
    ).status_code == 403
    response = await create(client, manager, path=f"/api/organizations/{org['id']}/users")
    assert response.status_code == 201, response.text
    target = response.json()["user"]["id"]
    temporary = response.json()["temporary_password"]
    membership = await db_session.get(OrganizationMember, (UUID(org["id"]), UUID(target)))
    assert membership.role == "member" and membership.state == "active"
    events = (
        await db_session.scalars(
            select(AdministrativeAuditEvent).where(
                AdministrativeAuditEvent.entity_id == UUID(target)
            )
        )
    ).all()
    assert [e.action for e in events] == ["user_created"]
    restricted = await login(client, "created@example.com", temporary)
    assert (
        await client.post(f"/api/users/{target}/temporary-password", headers=manager)
    ).status_code == 403
    admin = await administrator(client)
    reset = await client.post(f"/api/users/{target}/temporary-password", headers=admin)
    assert reset.status_code == 200 and reset.json()["temporary_password"] != temporary
    assert (await client.get("/api/users", headers=restricted)).status_code == 401
    from auth_helpers import authenticated_id

    admin_id = authenticated_id(admin)
    for headers in (manager, admin):
        assert (
            await client.post(
                f"/api/users/{admin_id}/block", headers=headers, json={"confirm": True}
            )
        ).status_code == 403
    assert (
        await client.post(f"/api/users/{admin_id}/temporary-password", headers=admin)
    ).status_code == 403
    ordinary = await authenticate(client, uuid4())
    assert (
        await client.post(f"/api/users/{target}/block", headers=ordinary, json={"confirm": True})
    ).status_code == 403
    assert (
        await client.post(f"/api/users/{target}/block", headers=admin, json={"confirm": False})
    ).status_code == 422
    assert (
        await client.post(f"/api/users/{target}/block", headers=admin, json={"confirm": True})
    ).status_code == 200
    reset_blocked = await client.post(f"/api/users/{target}/temporary-password", headers=admin)
    assert not reset_blocked.json()["user"]["is_active"]


async def test_disabled_public_actions_cannot_consume_legacy_tokens(client, db_session):
    target = await seed_account("legacy@example.com")
    now = datetime.now(UTC)
    pending = PendingRegistration(
        email="pending@example.com",
        password_hash=password_hash.hash(PASSWORD),
        first_name="Old",
        last_name="Request",
        expires_at=now + timedelta(hours=1),
        next_attempt_at=now,
    )
    reset_id = uuid4()
    token = reset_token(reset_id)
    db_session.add_all(
        [
            pending,
            PasswordReset(
                id=reset_id,
                user_id=target,
                email="legacy@example.com",
                token_hash=token_digest(token),
                expires_at=now + timedelta(hours=1),
                next_attempt_at=now,
            ),
        ]
    )
    await db_session.commit()
    for path, body in [
        (
            "register",
            {
                "email": "new@example.com",
                "password": PASSWORD,
                "first_name": "New",
                "last_name": "User",
            },
        ),
        ("verify-email", {"token": create_verification_token(pending), "password": PASSWORD}),
        ("password/reset-request", {"email": "legacy@example.com"}),
        ("password/reset", {"token": token, "new_password": "another safe permanent passphrase"}),
        ("deactivate", {"current_password": PASSWORD}),
    ]:
        assert (await client.post("/api/auth/" + path, json=body)).status_code == 404
    await login(client, "legacy@example.com", PASSWORD)
    assert await db_session.scalar(select(User).where(User.email == pending.email)) is None


async def test_user_list_cursor_filter_and_validation(client):
    admin = await administrator(client)
    for i in range(3):
        assert (await create(client, admin, f"user{i}@example.com")).status_code == 201
    first = await client.get("/api/users?q=New&limit=2", headers=admin)
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    second = await client.get(
        "/api/users", headers=admin, params={"q": "New", "limit": 2, "cursor": cursor}
    )
    assert len(second.json()["items"]) == 1
    assert (
        await client.get("/api/users", headers=admin, params={"q": "Other", "cursor": cursor})
    ).status_code == 422
    assert (await client.get("/api/users?cursor=bad", headers=admin)).status_code == 422
    assert (await client.get("/api/users")).status_code == 401
    assert (
        await client.post(
            "/api/users",
            headers=admin,
            json={"email": "invalid", "first_name": " ", "last_name": "Name", "password": PASSWORD},
        )
    ).status_code == 422


async def test_create_and_block_roll_back_when_audit_fails(client, db_session, monkeypatch):
    from app.services.administrative_audit import AdministrativeAuditService

    admin = await administrator(client)
    target = await seed_account("rollback@example.com")

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(AdministrativeAuditService, "record", fail)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        await create(client, admin)
    assert await db_session.scalar(select(User).where(User.email == "created@example.com")) is None
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        await client.post(f"/api/users/{target}/block", headers=admin, json={"confirm": True})
    assert (await db_session.get(User, target)).is_active


async def test_manager_self_block_and_archived_memberships(client, db_session):
    from auth_helpers import authenticated_id

    manager = await authenticate(client, uuid4())
    org = await create_organization(client, manager, "Manager")
    target = authenticated_id(manager)
    archived_org = await create_organization(client, manager, "Historical")
    membership = await db_session.get(OrganizationMember, (UUID(archived_org["id"]), target))
    membership.state = "archived"
    await db_session.commit()
    result = await client.post(
        f"/api/users/{target}/block", headers=manager, json={"confirm": True}
    )
    assert result.status_code == 200
    assert (await client.get("/api/users", headers=manager)).status_code == 401
    await db_session.refresh(membership)
    assert membership.state == "revoked" and membership.role == "member"
    assert org["id"] != archived_org["id"]


async def test_block_restricted_session_and_no_delivery_of_old_outboxes(client, db_session):
    from app.services.registration_mail import RegistrationMailService
    from app.services.reset_mail import ResetMailService

    admin = await administrator(client)
    response = await create(client, admin)
    target = response.json()["user"]["id"]
    restricted = await login(client, "created@example.com", response.json()["temporary_password"])
    cookie = client.cookies.get("__Secure-fst-refresh")
    assert (
        await client.post(f"/api/users/{target}/block", headers=admin, json={"confirm": True})
    ).status_code == 200
    assert (
        await client.post(
            "/api/auth/password/change",
            headers=restricted,
            json={
                "current_password": response.json()["temporary_password"],
                "new_password": PASSWORD,
            },
        )
    ).status_code == 401
    assert (
        await client.post("/api/auth/refresh", headers={"Cookie": f"__Secure-fst-refresh={cookie}"})
    ).status_code == 401
    assert await RegistrationMailService(db_session).process_one() is False
    assert await ResetMailService(db_session).process_one() is False
