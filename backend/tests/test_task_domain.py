from uuid import UUID

from httpx import AsyncClient


def auth(user_id: UUID) -> dict[str, str]:
    return {"X-User-ID": str(user_id)}


async def create_organization(client: AsyncClient, user_id: UUID, name: str) -> dict:
    response = await client.post("/api/organizations", json={"name": name}, headers=auth(user_id))
    assert response.status_code == 201
    return response.json()


async def create_project(
    client: AsyncClient, user_id: UUID, organization_id: str, name: str
) -> dict:
    response = await client.post(
        "/api/projects",
        json={"organization_id": organization_id, "name": name},
        headers=auth(user_id),
    )
    assert response.status_code == 201
    return response.json()


async def create_status(client: AsyncClient, user_id: UUID, project_id: str, name: str) -> dict:
    response = await client.post(
        f"/api/projects/{project_id}/statuses", json={"name": name}, headers=auth(user_id)
    )
    assert response.status_code == 201
    return response.json()


async def test_create_organization_project_status_and_task(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    user_id, _ = user_ids
    organization = await create_organization(client, user_id, "Acme")
    project = await create_project(client, user_id, organization["id"], "Tracker")
    status = await create_status(client, user_id, project["id"], "Backlog")

    response = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "First task", "status_id": status["id"]},
        headers=auth(user_id),
    )

    assert response.status_code == 201
    assert response.json()["project_id"] == project["id"]
    assert response.json()["status_id"] == status["id"]


async def test_statuses_are_returned_in_workflow_order(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    user_id, _ = user_ids
    organization = await create_organization(client, user_id, "Acme")
    project = await create_project(client, user_id, organization["id"], "Tracker")
    backlog = await create_status(client, user_id, project["id"], "Backlog")
    review = await create_status(client, user_id, project["id"], "Review")
    done = await create_status(client, user_id, project["id"], "Done")

    response = await client.post(
        f"/api/projects/{project['id']}/statuses/reorder",
        json={"status_ids": [review["id"], backlog["id"], done["id"]]},
        headers=auth(user_id),
    )
    assert response.status_code == 200

    response = await client.get(f"/api/projects/{project['id']}/statuses", headers=auth(user_id))
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Review", "Backlog", "Done"]


async def test_cross_project_status_is_rejected(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    user_id, _ = user_ids
    organization = await create_organization(client, user_id, "Acme")
    first_project = await create_project(client, user_id, organization["id"], "One")
    second_project = await create_project(client, user_id, organization["id"], "Two")
    second_status = await create_status(client, user_id, second_project["id"], "Backlog")

    response = await client.post(
        f"/api/projects/{first_project['id']}/tasks",
        json={"title": "Invalid task", "status_id": second_status["id"]},
        headers=auth(user_id),
    )
    assert response.status_code == 422


async def test_cross_organization_project_is_hidden(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    first_user, second_user = user_ids
    await create_organization(client, first_user, "First")
    second_org = await create_organization(client, second_user, "Second")
    second_project = await create_project(client, second_user, second_org["id"], "Private")

    response = await client.get(f"/api/projects/{second_project['id']}", headers=auth(first_user))
    assert response.status_code == 404

    response = await client.post(
        "/api/projects",
        json={"organization_id": second_org["id"], "name": "Intrusion"},
        headers=auth(first_user),
    )
    assert response.status_code == 404


async def test_authentication_and_validation_errors_are_consistent(client: AsyncClient) -> None:
    response = await client.post("/api/organizations", json={"name": "Acme"})
    assert response.status_code == 401

    response = await client.post(
        "/api/organizations", json={"name": ""}, headers={"X-User-ID": "not-a-uuid"}
    )
    assert response.status_code == 401
