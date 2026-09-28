from uuid import UUID, uuid4

from httpx import AsyncClient


async def authenticate(client: AsyncClient, user_id: UUID) -> dict[str, str]:
    email = f"{user_id}@example.com"
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    response = await client.post(
        "/api/auth/login",
        json={"email": email.upper(), "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_organization(client: AsyncClient, headers: dict[str, str], name: str) -> dict:
    response = await client.post("/api/organizations", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


async def create_project(
    client: AsyncClient, headers: dict[str, str], organization_id: str, name: str
) -> dict:
    response = await client.post(
        "/api/projects",
        json={"organization_id": organization_id, "name": name},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_status(
    client: AsyncClient, headers: dict[str, str], project_id: str, name: str
) -> dict:
    response = await client.post(
        f"/api/projects/{project_id}/statuses", json={"name": name}, headers=headers
    )
    assert response.status_code == 201
    return response.json()


async def test_create_organization_project_status_and_task(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    headers = await authenticate(client, user_ids[0])
    organization = await create_organization(client, headers, "Acme")
    project = await create_project(client, headers, organization["id"], "Tracker")
    project_status = await create_status(client, headers, project["id"], "Backlog")

    response = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "First task", "status_id": project_status["id"]},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["project_id"] == project["id"]
    assert response.json()["status_id"] == project_status["id"]


async def test_statuses_are_returned_in_workflow_order(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    headers = await authenticate(client, user_ids[0])
    organization = await create_organization(client, headers, "Acme")
    project = await create_project(client, headers, organization["id"], "Tracker")
    backlog = await create_status(client, headers, project["id"], "Backlog")
    review = await create_status(client, headers, project["id"], "Review")
    done = await create_status(client, headers, project["id"], "Done")

    response = await client.post(
        f"/api/projects/{project['id']}/statuses/reorder",
        json={"status_ids": [review["id"], backlog["id"], done["id"]]},
        headers=headers,
    )
    assert response.status_code == 200

    response = await client.get(f"/api/projects/{project['id']}/statuses", headers=headers)
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Review", "Backlog", "Done"]


async def test_cross_project_status_is_rejected(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    headers = await authenticate(client, user_ids[0])
    organization = await create_organization(client, headers, "Acme")
    first_project = await create_project(client, headers, organization["id"], "One")
    second_project = await create_project(client, headers, organization["id"], "Two")
    second_status = await create_status(client, headers, second_project["id"], "Backlog")

    response = await client.post(
        f"/api/projects/{first_project['id']}/tasks",
        json={"title": "Invalid task", "status_id": second_status["id"]},
        headers=headers,
    )
    assert response.status_code == 422


async def test_cross_organization_project_is_hidden(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    first_headers = await authenticate(client, user_ids[0])
    second_headers = await authenticate(client, user_ids[1])
    await create_organization(client, first_headers, "First")
    second_org = await create_organization(client, second_headers, "Second")
    second_project = await create_project(client, second_headers, second_org["id"], "Private")

    response = await client.get(f"/api/projects/{second_project['id']}", headers=first_headers)
    assert response.status_code == 404

    response = await client.post(
        "/api/projects",
        json={"organization_id": second_org["id"], "name": "Intrusion"},
        headers=first_headers,
    )
    assert response.status_code == 404


async def test_protected_endpoint_requires_bearer_token(client: AsyncClient) -> None:
    response = await client.post("/api/organizations", json={"name": "Acme"})
    assert response.status_code == 401

    response = await client.post(
        "/api/organizations",
        json={"name": "Acme"},
        headers={"X-User-ID": str(uuid4())},
    )
    assert response.status_code == 401


async def test_membership_authorization_ownership_and_soft_delete_lifecycle(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    owner_headers = await authenticate(client, user_ids[0])
    member_headers = await authenticate(client, user_ids[1])
    outsider_id = uuid4()
    outsider_headers = await authenticate(client, outsider_id)
    member_email = f"{user_ids[1]}@example.com"
    outsider_email = f"{outsider_id}@example.com"

    organization = await create_organization(client, owner_headers, "Acme")
    organization_id = organization["id"]
    add_member = await client.post(
        f"/api/organizations/{organization_id}/members",
        json={"email": member_email},
        headers=owner_headers,
    )
    assert add_member.status_code == 200
    assert add_member.json()["email"] == member_email
    member_user_id = add_member.json()["id"]

    duplicate_member = await client.post(
        f"/api/organizations/{organization_id}/members",
        json={"email": member_email.upper()},
        headers=owner_headers,
    )
    assert duplicate_member.status_code == 200

    denied_add = await client.post(
        f"/api/organizations/{organization_id}/members",
        json={"email": outsider_email},
        headers=member_headers,
    )
    assert denied_add.status_code == 403

    outsider_view = await client.get(
        f"/api/organizations/{organization_id}", headers=outsider_headers
    )
    assert outsider_view.status_code == 404

    project = await create_project(client, owner_headers, organization_id, "Private project")
    project_id = project["id"]
    project_member = await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": member_email},
        headers=owner_headers,
    )
    assert project_member.status_code == 200

    member_project_view = await client.get(f"/api/projects/{project_id}", headers=member_headers)
    assert member_project_view.status_code == 200
    non_owner_manage = await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": outsider_email},
        headers=member_headers,
    )
    assert non_owner_manage.status_code == 403

    transfer_project = await client.post(
        f"/api/projects/{project_id}/transfer-ownership",
        json={"email": member_email},
        headers=owner_headers,
    )
    assert transfer_project.status_code == 200
    assert transfer_project.json()["owner_id"] == member_user_id

    transfer_organization = await client.post(
        f"/api/organizations/{organization_id}/transfer-ownership",
        json={"email": member_email},
        headers=owner_headers,
    )
    assert transfer_organization.status_code == 200
    assert transfer_organization.json()["owner_id"] == member_user_id

    add_outsider_to_org = await client.post(
        f"/api/organizations/{organization_id}/members",
        json={"email": outsider_email},
        headers=member_headers,
    )
    assert add_outsider_to_org.status_code == 200
    add_outsider_to_project = await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": outsider_email},
        headers=member_headers,
    )
    assert add_outsider_to_project.status_code == 200

    remove_old_owner = await client.delete(
        f"/api/projects/{project_id}/members/{project['owner_id']}", headers=member_headers
    )
    assert remove_old_owner.status_code == 200
    removed_owner_view = await client.get(f"/api/projects/{project_id}", headers=owner_headers)
    assert removed_owner_view.status_code == 404

    missing_confirmation = await client.request(
        "DELETE", f"/api/projects/{project_id}", json={"confirm": False}, headers=member_headers
    )
    assert missing_confirmation.status_code == 422
    deleted_project = await client.request(
        "DELETE", f"/api/projects/{project_id}", json={"confirm": True}, headers=member_headers
    )
    assert deleted_project.status_code == 204
    hidden_project = await client.get(f"/api/projects/{project_id}", headers=member_headers)
    assert hidden_project.status_code == 404

    restored_project = await client.post(
        f"/api/projects/{project_id}/restore", headers=member_headers
    )
    assert restored_project.status_code == 200

    deleted_organization = await client.request(
        "DELETE",
        f"/api/organizations/{organization_id}",
        json={"confirm": True},
        headers=member_headers,
    )
    assert deleted_organization.status_code == 204
    hidden_organization = await client.get(
        f"/api/organizations/{organization_id}", headers=member_headers
    )
    assert hidden_organization.status_code == 404
    restore_organization = await client.post(
        f"/api/organizations/{organization_id}/restore", headers=member_headers
    )
    assert restore_organization.status_code == 200

    await client.request(
        "DELETE", f"/api/projects/{project_id}", json={"confirm": True}, headers=member_headers
    )
    await client.request(
        "DELETE",
        f"/api/organizations/{organization_id}",
        json={"confirm": True},
        headers=member_headers,
    )
    restore_while_organization_deleted = await client.post(
        f"/api/projects/{project_id}/restore", headers=member_headers
    )
    assert restore_while_organization_deleted.status_code == 409
    await client.post(f"/api/organizations/{organization_id}/restore", headers=member_headers)
    restored_after_parent = await client.post(
        f"/api/projects/{project_id}/restore", headers=member_headers
    )
    assert restored_after_parent.status_code == 200
