from uuid import UUID, uuid4

from httpx import AsyncClient


async def authenticate(client: AsyncClient, user_id: UUID) -> dict[str, str]:
    email = f"{user_id}@example.com"
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert response.status_code == 201
    response = await client.post(
        "/api/auth/login",
        json={
            "email": email.upper(),
            "password": "correct horse battery staple",
            "first_name": "Test",
            "last_name": "User",
        },
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
    statuses = (await client.get(f"/api/projects/{project['id']}/statuses", headers=headers)).json()
    backlog, in_progress, done = statuses
    review = await create_status(client, headers, project["id"], "Review")

    response = await client.post(
        f"/api/projects/{project['id']}/statuses/reorder",
        json={"status_ids": [review["id"], backlog["id"], in_progress["id"], done["id"]]},
        headers=headers,
    )
    assert response.status_code == 200

    response = await client.get(f"/api/projects/{project['id']}/statuses", headers=headers)
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "Review",
        "Backlog",
        "In Progress",
        "Done",
    ]


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


async def test_board_move_history_and_independent_cursor_page(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    owner_headers = await authenticate(client, user_ids[0])
    member_headers = await authenticate(client, user_ids[1])
    organization = await create_organization(client, owner_headers, "Acme")
    project = await create_project(client, owner_headers, organization["id"], "Tracker")
    statuses = (
        await client.get(f"/api/projects/{project['id']}/statuses", headers=owner_headers)
    ).json()
    backlog, in_progress, done = statuses

    await client.post(
        f"/api/organizations/{organization['id']}/members",
        json={"email": f"{user_ids[1]}@example.com"},
        headers=owner_headers,
    )
    add_member = await client.post(
        f"/api/projects/{project['id']}/members",
        json={"email": f"{user_ids[1]}@example.com"},
        headers=owner_headers,
    )
    assert add_member.status_code == 200
    task = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "Move me", "status_id": backlog["id"]},
        headers=owner_headers,
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    moved = await client.patch(
        f"/api/tasks/{task_id}",
        json={"status_id": in_progress["id"]},
        headers=member_headers,
    )
    assert moved.status_code == 200
    history = await client.get(f"/api/tasks/{task_id}/history", headers=owner_headers)
    assert history.status_code == 200
    assert len(history.json()["entries"]) == 1
    assert history.json()["entries"][0]["from_status_id"] == backlog["id"]
    assert history.json()["entries"][0]["to_status_id"] == in_progress["id"]
    no_op = await client.patch(
        f"/api/tasks/{task_id}",
        json={"status_id": in_progress["id"]},
        headers=member_headers,
    )
    assert no_op.status_code == 200
    history_after_no_op = await client.get(f"/api/tasks/{task_id}/history", headers=owner_headers)
    assert len(history_after_no_op.json()["entries"]) == 1

    board = await client.get(f"/api/projects/{project['id']}/board?limit=1", headers=member_headers)
    assert board.status_code == 200
    assert [column["status"]["name"] for column in board.json()["columns"]] == [
        "Backlog",
        "In Progress",
        "Done",
    ]
    in_progress_column = next(
        column for column in board.json()["columns"] if column["status"]["id"] == in_progress["id"]
    )
    assert in_progress_column["tasks"][0]["id"] == task_id


async def test_status_archive_is_owner_only_and_requires_empty_non_last_status(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    owner_headers = await authenticate(client, user_ids[0])
    member_headers = await authenticate(client, user_ids[1])
    organization = await create_organization(client, owner_headers, "Acme")
    project = await create_project(client, owner_headers, organization["id"], "Tracker")
    await client.post(
        f"/api/organizations/{organization['id']}/members",
        json={"email": f"{user_ids[1]}@example.com"},
        headers=owner_headers,
    )
    member = await client.post(
        f"/api/projects/{project['id']}/members",
        json={"email": f"{user_ids[1]}@example.com"},
        headers=owner_headers,
    )
    assert member.status_code == 200
    statuses = (
        await client.get(f"/api/projects/{project['id']}/statuses", headers=owner_headers)
    ).json()
    backlog, in_progress, done = statuses

    denied = await client.delete(
        f"/api/projects/{project['id']}/statuses/{done['id']}", headers=member_headers
    )
    assert denied.status_code == 403
    task = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "Blocking task", "status_id": done["id"]},
        headers=owner_headers,
    )
    assert task.status_code == 201
    blocked = await client.delete(
        f"/api/projects/{project['id']}/statuses/{done['id']}", headers=owner_headers
    )
    assert blocked.status_code == 409
    await client.patch(
        f"/api/tasks/{task.json()['id']}",
        json={"status_id": backlog["id"]},
        headers=owner_headers,
    )
    archived = await client.delete(
        f"/api/projects/{project['id']}/statuses/{done['id']}", headers=owner_headers
    )
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    archive = await client.get(
        f"/api/projects/{project['id']}/statuses/archive", headers=owner_headers
    )
    assert [item["id"] for item in archive.json()] == [done["id"]]
    restored = await client.post(
        f"/api/projects/{project['id']}/statuses/{done['id']}/restore", headers=owner_headers
    )
    assert restored.status_code == 200
    assert restored.json()["is_active"] is True
    await client.patch(
        f"/api/tasks/{task.json()['id']}",
        json={"status_id": done["id"]},
        headers=owner_headers,
    )

    for status_item in (backlog, in_progress):
        response = await client.delete(
            f"/api/projects/{project['id']}/statuses/{status_item['id']}", headers=owner_headers
        )
        assert response.status_code == 200
    last = await client.delete(
        f"/api/projects/{project['id']}/statuses/{done['id']}", headers=owner_headers
    )
    assert last.status_code == 409


async def test_task_participants_watchers_and_notifications(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    owner_login_id, organization_login_id = user_ids
    owner_headers = await authenticate(client, owner_login_id)
    organization_user_headers = await authenticate(client, organization_login_id)
    outsider_login_id = uuid4()
    outsider_headers = await authenticate(client, outsider_login_id)
    organization = await create_organization(client, owner_headers, "Acme")
    owner_id = UUID(organization["owner_id"])
    project = await create_project(client, owner_headers, organization["id"], "Tracker")
    statuses = (
        await client.get(f"/api/projects/{project['id']}/statuses", headers=owner_headers)
    ).json()
    backlog, in_progress, _ = statuses

    added_to_org = await client.post(
        f"/api/organizations/{organization['id']}/members",
        json={"email": f"{organization_login_id}@example.com"},
        headers=owner_headers,
    )
    assert added_to_org.status_code == 200
    organization_user_id = UUID(added_to_org.json()["id"])

    task = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "Participants", "status_id": backlog["id"]},
        headers=owner_headers,
    )
    assert task.status_code == 201
    task_body = task.json()
    task_id = task_body["id"]
    assert task_body["created_by"] == str(owner_id)
    assert task_body["reporter_id"] == str(owner_id)
    assert task_body["assignee_id"] is None
    assert task_body["watchers"] == []

    outsider_assignment = await client.patch(
        f"/api/tasks/{task_id}",
        json={"assignee_id": str(outsider_login_id)},
        headers=owner_headers,
    )
    assert outsider_assignment.status_code == 422

    add_watcher = await client.post(
        f"/api/tasks/{task_id}/watchers",
        json={"user_id": str(organization_user_id)},
        headers=owner_headers,
    )
    assert add_watcher.status_code == 200
    assert [item["id"] for item in add_watcher.json()] == [str(organization_user_id)]
    duplicate_watcher = await client.post(
        f"/api/tasks/{task_id}/watchers",
        json={"user_id": str(organization_user_id)},
        headers=owner_headers,
    )
    assert duplicate_watcher.status_code == 200
    project_members = await client.get(
        f"/api/projects/{project['id']}/members", headers=owner_headers
    )
    assert organization_user_id in {UUID(item["id"]) for item in project_members.json()}

    self_assigned = await client.patch(
        f"/api/tasks/{task_id}",
        json={"assignee_id": str(organization_user_id)},
        headers=organization_user_headers,
    )
    assert self_assigned.status_code == 200
    assert self_assigned.json()["assignee_id"] == str(organization_user_id)

    owner_changes_title = await client.patch(
        f"/api/tasks/{task_id}",
        json={"title": "Participants updated", "status_id": in_progress["id"]},
        headers=owner_headers,
    )
    assert owner_changes_title.status_code == 200
    owner_changes_participants = await client.patch(
        f"/api/tasks/{task_id}",
        json={
            "description": "Updated details",
            "reporter_id": str(organization_user_id),
            "assignee_id": None,
        },
        headers=owner_headers,
    )
    assert owner_changes_participants.status_code == 200
    notifications = await client.get("/api/notifications", headers=organization_user_headers)
    assert notifications.status_code == 200
    notification_types = {item["event_type"] for item in notifications.json()}
    required_notification_types = {
        "title_changed",
        "status_changed",
        "description_changed",
        "reporter_changed",
        "assignee_changed",
    }
    assert required_notification_types.issubset(notification_types)
    unread = await client.get("/api/notifications/unread-count", headers=organization_user_headers)
    assert unread.status_code == 200
    unread_before_open = unread.json()["count"]
    assert unread_before_open >= 2

    notification_id = notifications.json()[0]["id"]
    opened = await client.post(
        f"/api/notifications/{notification_id}/open", headers=organization_user_headers
    )
    assert opened.status_code == 200
    assert opened.json()["read_at"] is not None
    unread_after_open = await client.get(
        "/api/notifications/unread-count", headers=organization_user_headers
    )
    assert unread_after_open.json()["count"] == unread_before_open - 1
    opened_again = await client.post(
        f"/api/notifications/{notification_id}/open", headers=organization_user_headers
    )
    assert opened_again.status_code == 200
    assert (
        await client.get("/api/notifications/unread-count", headers=organization_user_headers)
    ).json()["count"] == unread_after_open.json()["count"]

    forbidden_open = await client.post(
        f"/api/notifications/{notification_id}/open", headers=outsider_headers
    )
    assert forbidden_open.status_code == 404
    removed_watcher = await client.delete(
        f"/api/tasks/{task_id}/watchers/{organization_user_id}", headers=organization_user_headers
    )
    assert removed_watcher.status_code == 200
    remaining_members = await client.get(
        f"/api/projects/{project['id']}/members", headers=owner_headers
    )
    assert organization_user_id in {UUID(item["id"]) for item in remaining_members.json()}


async def test_task_participant_permission_matrix_and_organization_isolation(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    owner_login_id, member_login_id = user_ids
    regular_login_id = uuid4()
    foreign_login_id = uuid4()
    owner_headers = await authenticate(client, owner_login_id)
    member_headers = await authenticate(client, member_login_id)
    regular_headers = await authenticate(client, regular_login_id)
    foreign_headers = await authenticate(client, foreign_login_id)

    organization = await create_organization(client, owner_headers, "Acme")
    organization_id = organization["id"]
    member_user_id = UUID(int=0)
    regular_user_id = UUID(int=0)
    for login_id in (member_login_id, regular_login_id):
        response = await client.post(
            f"/api/organizations/{organization_id}/members",
            json={"email": f"{login_id}@example.com"},
            headers=owner_headers,
        )
        assert response.status_code == 200
        if login_id == member_login_id:
            member_user_id = UUID(response.json()["id"])
        else:
            regular_user_id = UUID(response.json()["id"])

    project = await create_project(client, owner_headers, organization_id, "Tracker")
    project_id = project["id"]
    for login_id in (member_login_id, regular_login_id):
        response = await client.post(
            f"/api/projects/{project_id}/members",
            json={"email": f"{login_id}@example.com"},
            headers=owner_headers,
        )
        assert response.status_code == 200
    statuses = (
        await client.get(f"/api/projects/{project_id}/statuses", headers=owner_headers)
    ).json()
    task = await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Permission matrix", "status_id": statuses[0]["id"]},
        headers=owner_headers,
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    self_assigned = await client.patch(
        f"/api/tasks/{task_id}",
        json={"assignee_id": str(member_user_id)},
        headers=member_headers,
    )
    assert self_assigned.status_code == 200
    regular_assignee_change = await client.patch(
        f"/api/tasks/{task_id}",
        json={"assignee_id": str(regular_user_id)},
        headers=regular_headers,
    )
    assert regular_assignee_change.status_code == 403
    regular_reporter_change = await client.patch(
        f"/api/tasks/{task_id}",
        json={"reporter_id": str(regular_user_id)},
        headers=regular_headers,
    )
    assert regular_reporter_change.status_code == 403

    owner_reporter_change = await client.patch(
        f"/api/tasks/{task_id}",
        json={"reporter_id": str(member_user_id)},
        headers=owner_headers,
    )
    assert owner_reporter_change.status_code == 200
    reporter_reporter_change = await client.patch(
        f"/api/tasks/{task_id}",
        json={"reporter_id": str(UUID(organization["owner_id"]))},
        headers=member_headers,
    )
    assert reporter_reporter_change.status_code == 200

    self_watching = await client.post(
        f"/api/tasks/{task_id}/watchers", json={}, headers=regular_headers
    )
    assert self_watching.status_code == 200
    stopped_watching = await client.delete(
        f"/api/tasks/{task_id}/watchers/{regular_user_id}", headers=regular_headers
    )
    assert stopped_watching.status_code == 200

    foreign_organization = await create_organization(client, foreign_headers, "Foreign")
    foreign_user_id = UUID(foreign_organization["owner_id"])
    foreign_watcher = await client.post(
        f"/api/tasks/{task_id}/watchers",
        json={"user_id": str(foreign_user_id)},
        headers=owner_headers,
    )
    assert foreign_watcher.status_code == 422
    foreign_task_access = await client.get(f"/api/tasks/{task_id}", headers=foreign_headers)
    assert foreign_task_access.status_code == 404
