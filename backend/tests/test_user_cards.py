from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from auth_helpers import authenticated_id
from sqlalchemy import select
from test_task_domain import authenticate, create_organization, create_project
from test_user_lifecycle import administrator

from app.models import OrganizationMember, User
from app.models.administrative_audit import AdministrativeAuditEvent
from app.models.email_change import EmailChangeRequest
from app.services.email_change import email_change_token


async def request_change(client, headers, email="changed@example.com"):
    return await client.post("/api/users/me/email-change", headers=headers, json={"email": email})


async def token_for(db_session, headers):
    row = await db_session.get(
        EmailChangeRequest, authenticated_id(headers), populate_existing=True
    )
    return email_change_token(row.request_id)


async def confirm(client, headers, token):
    return await client.post(
        "/api/users/me/email-change/confirm", headers=headers, json={"token": token}
    )


async def test_cards_all_active_memberships_without_resource_access(client, db_session):
    target = await authenticate(client, uuid4())
    visitor = await authenticate(client, uuid4())
    org = await create_organization(client, target, "Visible name, private resource")
    project = await create_project(client, target, org["id"], "Private project")
    target_id = authenticated_id(target)
    card = await client.get(f"/api/users/{target_id}", headers=visitor)
    assert card.status_code == 200, card.text
    assert set(card.json()) == {
        "id",
        "first_name",
        "last_name",
        "is_active",
        "created_at",
        "capabilities",
    }
    assert not card.json()["capabilities"]["edit_profile"]
    for scope, resource in (("organizations", org), ("projects", project)):
        response = await client.get(f"/api/users/{target_id}/{scope}", headers=visitor)
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["name"] == resource["name"] and not item["can_open"]
        assert (
            await client.get(f"/api/{scope}/{resource['id']}", headers=visitor)
        ).status_code == 404
    org_member = await db_session.get(OrganizationMember, (UUID(org["id"]), target_id))
    org_member.state = "archived"
    await db_session.commit()
    for scope in ("organizations", "projects"):
        assert (await client.get(f"/api/users/{target_id}/{scope}", headers=visitor)).json()[
            "items"
        ] == []
    row = await db_session.get(User, target_id)
    row.is_active = False
    await db_session.commit()
    assert not (await client.get(f"/api/users/{target_id}", headers=visitor)).json()["is_active"]
    assert (await client.get(f"/api/users/{target_id}", headers=target)).status_code == 401
    assert (await client.get(f"/api/users/{target_id}")).status_code == 401
    assert (await client.get(f"/api/users/{uuid4()}", headers=visitor)).status_code == 404


async def test_membership_pagination_binding_and_can_open(client, db_session):
    target = await authenticate(client, uuid4())
    target_id = authenticated_id(target)
    for index in range(3):
        await create_organization(client, target, f"Org {index}")
    url = f"/api/users/{target_id}/organizations"
    page = (await client.get(url + "?limit=1", headers=target)).json()
    assert len(page["items"]) == 1 and page["items"][0]["can_open"]
    cursor = page["next_cursor"]
    next_page = (await client.get(url, params={"cursor": cursor}, headers=target)).json()
    assert len(next_page["items"]) == 2
    assert page["items"][0]["id"] not in [item["id"] for item in next_page["items"]]
    assert (
        await client.get(
            f"/api/users/{target_id}/projects", params={"cursor": cursor}, headers=target
        )
    ).status_code == 422
    assert (await client.get(url + "?cursor=broken", headers=target)).status_code == 422


async def test_profile_permissions_atomic_audit_and_noop(client, db_session, monkeypatch):
    admin = await administrator(client)
    owner = await authenticate(client, uuid4())
    manager = await authenticate(client, uuid4())
    await create_organization(client, manager, "Managed")
    target_id = authenticated_id(owner)
    body = {"first_name": "Updated", "last_name": "Name"}
    url = f"/api/users/{target_id}/profile"
    assert (await client.patch(url, headers=manager, json=body)).status_code == 403
    assert (
        await client.patch("/api/users/me/profile", headers=owner, json=body)
    ).status_code == 200
    assert (await client.patch(url, headers=admin, json=body)).status_code == 200
    events = list(
        await db_session.scalars(
            select(AdministrativeAuditEvent).where(
                AdministrativeAuditEvent.action == "profile_updated"
            )
        )
    )
    assert len(events) == 1 and len(events[0].changes) == 2
    assert (
        await client.patch(url, headers=admin, json={**body, "email": "bypass@example.com"})
    ).status_code == 422
    from app.services.administrative_audit import AdministrativeAuditService

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(AdministrativeAuditService, "record", fail)
    with pytest.raises(RuntimeError):
        await client.patch(url, headers=admin, json={**body, "first_name": "Rollback"})
    assert (await client.get(f"/api/users/{target_id}", headers=owner)).json()[
        "first_name"
    ] == "Updated"


async def test_email_latest_expiry_owner_conflict_and_replay(client, db_session):
    owner = await authenticate(client, uuid4())
    other = await authenticate(client, uuid4())
    identifier = authenticated_id(owner)
    user = await db_session.get(User, identifier)
    old_email = user.email
    assert (await request_change(client, owner, old_email)).status_code == 422
    response = await request_change(client, owner)
    assert response.status_code == 202, response.text
    expires = datetime.fromisoformat(response.json()["expires_at"])
    assert timedelta(hours=5, minutes=59) < expires - datetime.now(UTC) <= timedelta(hours=6)
    first = await token_for(db_session, owner)
    assert (await confirm(client, other, first)).status_code == 422
    assert (await request_change(client, owner, "Latest@EXAMPLE.COM")).status_code == 202
    latest = await token_for(db_session, owner)
    assert first != latest
    assert (await confirm(client, owner, first)).status_code == 422
    pending = await db_session.get(EmailChangeRequest, identifier, populate_existing=True)
    assert pending.new_email == "latest@example.com" and first not in str(pending.__dict__)
    pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert (await confirm(client, owner, latest)).status_code == 422
    assert (await request_change(client, owner)).status_code == 202
    latest = await token_for(db_session, owner)
    assert (await confirm(client, owner, latest)).status_code == 204
    assert (await confirm(client, owner, latest)).status_code == 422
    user = await db_session.get(User, identifier, populate_existing=True)
    assert user.email == "changed@example.com"
    assert (await client.get("/api/users/me/profile", headers=owner)).status_code == 200
    assert (await request_change(client, other)).status_code == 409
    assert not list(await db_session.scalars(select(AdministrativeAuditEvent)))
    # Validation must not echo an oversized credential.
    secret = "private-token" * 100
    response = await confirm(client, owner, secret)
    assert response.status_code == 422 and secret not in response.text


async def test_direct_email_conflict_cancellation_and_admin_protection(client, db_session):
    admin = await administrator(client)
    owner = await authenticate(client, uuid4())
    other = await authenticate(client, uuid4())
    owner_id, other_id = authenticated_id(owner), authenticated_id(other)
    url = f"/api/users/{owner_id}/email"
    assert (await request_change(client, owner)).status_code == 202
    token = await token_for(db_session, owner)
    assert (
        await client.patch(url, headers=other, json={"email": "direct@example.com"})
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/users/{other_id}/email", headers=admin, json={"email": "changed@example.com"}
        )
    ).status_code == 200
    assert (await confirm(client, owner, token)).status_code == 409
    result = await client.patch(url, headers=admin, json={"email": "direct@example.com"})
    assert result.status_code == 200 and result.json()["email"] == "direct@example.com"
    assert (await confirm(client, owner, token)).status_code == 422
    assert (await request_change(client, admin)).status_code == 403
    assert (await confirm(client, admin, token)).status_code == 403
    assert (
        await client.patch(
            f"/api/users/{authenticated_id(admin)}/email",
            headers=admin,
            json={"email": "forbidden@example.com"},
        )
    ).status_code == 403
    assert not list(await db_session.scalars(select(AdministrativeAuditEvent)))


@pytest.mark.parametrize("action", ["block", "temporary-password"])
async def test_lifecycle_cancels_email_request(client, db_session, action):
    admin = await administrator(client)
    owner = await authenticate(client, uuid4())
    assert (await request_change(client, owner)).status_code == 202
    response = await client.post(
        f"/api/users/{authenticated_id(owner)}/{action}",
        headers=admin,
        json={"confirm": True} if action == "block" else {},
    )
    assert response.status_code == 200
    assert (
        await db_session.get(EmailChangeRequest, authenticated_id(owner), populate_existing=True)
        is None
    )
