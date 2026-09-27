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
