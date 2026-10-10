from datetime import date
from uuid import UUID, uuid4

from auth_helpers import authenticated_id, seed_account
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from test_task_domain import create_organization, create_project

from app.services.deadlines import DeadlineService


async def authenticate(client: AsyncClient, login_id: UUID) -> dict[str, str]:
    email = f"{login_id}@example.com"
    await seed_account(email, first_name="Planning")
    logged_in = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert logged_in.status_code == 200
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


async def setup_project(
    client: AsyncClient,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict, dict, dict]:
    owner_login, assignee_login, regular_login = uuid4(), uuid4(), uuid4()
    owner_headers = await authenticate(client, owner_login)
    assignee_headers = await authenticate(client, assignee_login)
    regular_headers = await authenticate(client, regular_login)

    organization = await create_organization(client, owner_headers, "Planning")
    member_ids: list[str] = []
    for login_id in (assignee_login, regular_login):
        response = await client.post(
            f"/api/organizations/{organization['id']}/members",
            json={"email": f"{login_id}@example.com"},
            headers=owner_headers,
        )
        assert response.status_code == 200
        member_ids.append(response.json()["id"])

    project = await create_project(client, owner_headers, organization["id"], "Roadmap")
    response = await client.post(
        f"/api/projects/{project['id']}/members",
        json={"email": f"{regular_login}@example.com"},
        headers=owner_headers,
    )
    assert response.status_code == 200
    status = (
        await client.get(f"/api/projects/{project['id']}/statuses", headers=owner_headers)
    ).json()[0]
    users = {
        "owner": str(authenticated_id(owner_headers)),
        "assignee": member_ids[0],
        "regular": member_ids[1],
    }
    return owner_headers, assignee_headers, regular_headers, project, status, users


async def test_story_points_validation_permissions_history_and_no_notification(
    client: AsyncClient,
) -> None:
    owner, assignee, regular, project, status, users = await setup_project(client)

    without_estimate = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "Unestimated", "status_id": status["id"]},
        headers=owner,
    )
    assert without_estimate.status_code == 201
    assert without_estimate.json()["story_points"] is None
    assert without_estimate.json()["due_date"] is None

    for value in (1, 2, 3, 5, 8, 13, 21):
        response = await client.post(
            f"/api/projects/{project['id']}/tasks",
            json={"title": f"Estimate {value}", "status_id": status["id"], "story_points": value},
            headers=owner,
        )
        assert response.status_code == 201
        assert response.json()["story_points"] == value

    for value in (0, -1, 4, 34, 1.5, "5"):
        response = await client.patch(
            f"/api/tasks/{without_estimate.json()['id']}",
            json={"story_points": value},
            headers=owner,
        )
        assert response.status_code == 422

    assigned = await client.patch(
        f"/api/tasks/{without_estimate.json()['id']}",
        json={"assignee_id": users["assignee"]},
        headers=owner,
    )
    assert assigned.status_code == 200

    forbidden = await client.patch(
        f"/api/tasks/{without_estimate.json()['id']}",
        json={"story_points": 3},
        headers=regular,
    )
    assert forbidden.status_code == 403

    changed = await client.patch(
        f"/api/tasks/{without_estimate.json()['id']}",
        json={"story_points": 5},
        headers=assignee,
    )
    assert changed.status_code == 200
    assert changed.json()["story_points"] == 5

    unchanged = await client.patch(
        f"/api/tasks/{without_estimate.json()['id']}",
        json={"description": "Planning notes"},
        headers=assignee,
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["story_points"] == 5

    removed = await client.patch(
        f"/api/tasks/{without_estimate.json()['id']}",
        json={"story_points": None},
        headers=owner,
    )
    assert removed.status_code == 200
    assert removed.json()["story_points"] is None

    history = await client.get(f"/api/tasks/{without_estimate.json()['id']}/history", headers=owner)
    planning_entries = [
        entry
        for entry in history.json()["entries"]
        if entry["event_type"] == "story_points_changed"
    ]
    assert [(entry["old_value"], entry["new_value"]) for entry in planning_entries] == [
        ("5", None),
        (None, "5"),
    ]
    notifications = await client.get("/api/notifications", headers=assignee)
    assert all(item["event_type"] != "story_points_changed" for item in notifications.json())


async def test_deadline_notifications_status_permissions_and_worker_idempotency(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner, assignee, regular, project, status, users = await setup_project(client)
    task = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "title": "Release",
            "status_id": status["id"],
            "assignee_id": users["assignee"],
            "due_date": "2026-10-15",
        },
        headers=owner,
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    watcher = await client.post(
        f"/api/tasks/{task_id}/watchers",
        json={"user_id": users["assignee"]},
        headers=owner,
    )
    assert watcher.status_code == 200

    forbidden_deadline = await client.patch(
        f"/api/tasks/{task_id}",
        json={"due_date": "2026-10-16"},
        headers=regular,
    )
    assert forbidden_deadline.status_code == 403

    changed = await client.patch(
        f"/api/tasks/{task_id}",
        json={"due_date": "2026-10-16"},
        headers=owner,
    )
    assert changed.status_code == 200
    notifications = await client.get("/api/notifications", headers=assignee)
    deadline_changes = [
        item for item in notifications.json() if item["event_type"] == "due_date_changed"
    ]
    assert len(deadline_changes) == 2
    assert {item["event_data"] for item in deadline_changes} == {
        f'{{"project_id":"{project["id"]}","due_date":"2026-10-15"}}',
        f'{{"project_id":"{project["id"]}","due_date":"2026-10-16"}}',
    }

    assert await DeadlineService(db_session).process_due(date(2026, 10, 16)) == 1
    assert await DeadlineService(db_session).process_due(date(2026, 10, 16)) == 0
    notifications = await client.get("/api/notifications", headers=assignee)
    assert len([item for item in notifications.json() if item["event_type"] == "deadline_due"]) == 1

    member_status_change = await client.patch(
        f"/api/projects/{project['id']}/statuses/{status['id']}",
        json={"is_completed": True},
        headers=regular,
    )
    assert member_status_change.status_code == 403
    completed = await client.patch(
        f"/api/projects/{project['id']}/statuses/{status['id']}",
        json={"is_completed": True},
        headers=owner,
    )
    assert completed.status_code == 200
    assert completed.json()["is_completed"] is True

    second_task = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "title": "Already complete",
            "status_id": status["id"],
            "assignee_id": users["assignee"],
            "due_date": "2026-10-17",
        },
        headers=owner,
    )
    assert second_task.status_code == 201
    assert await DeadlineService(db_session).process_due(date(2026, 10, 18)) == 0

    active_status = await client.post(
        f"/api/projects/{project['id']}/statuses",
        json={"name": "Still active"},
        headers=owner,
    )
    assert active_status.status_code == 201
    revoked_task = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "title": "Access revoked",
            "status_id": active_status.json()["id"],
            "assignee_id": users["assignee"],
            "due_date": "2026-10-18",
        },
        headers=owner,
    )
    assert revoked_task.status_code == 201
    revoked = await client.delete(
        f"/api/projects/{project['id']}/members/{users['assignee']}",
        headers=owner,
    )
    assert revoked.status_code == 200
    assert await DeadlineService(db_session).process_due(date(2026, 10, 18)) == 0

    no_assignee = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "title": "No assignee",
            "status_id": active_status.json()["id"],
            "due_date": "2026-10-18",
        },
        headers=owner,
    )
    assert no_assignee.status_code == 201
    assert await DeadlineService(db_session).process_due(date(2026, 10, 18)) == 0

    history = await client.get(f"/api/tasks/{task_id}/history", headers=owner)
    deadline_entries = [
        entry for entry in history.json()["entries"] if entry["event_type"] == "due_date_changed"
    ]
    assert [(entry["old_value"], entry["new_value"]) for entry in deadline_entries] == [
        ("2026-10-15", "2026-10-16"),
        (None, "2026-10-15"),
    ]


async def test_priority_permissions_history_profiles_and_no_notification(
    client: AsyncClient,
) -> None:
    owner, assignee, regular, project, status, users = await setup_project(client)
    for value in ("low", "normal", "major", "critical"):
        created = await client.post(
            f"/api/projects/{project['id']}/tasks",
            json={"title": f"Create {value}", "status_id": status["id"], "priority": value},
            headers=owner,
        )
        assert created.status_code == 201
        assert created.json()["priority"] == value

    task = await client.post(
        f"/api/projects/{project['id']}/tasks",
        json={
            "title": "Prioritized work",
            "status_id": status["id"],
            "assignee_id": users["assignee"],
        },
        headers=owner,
    )
    assert task.status_code == 201
    task_body = task.json()
    assert task_body["priority"] is None
    assert task_body["reporter"] == {
        "is_active": True,
        "id": users["owner"],
        "first_name": "Planning",
        "last_name": "User",
    }
    assert task_body["assignee"] == {
        "is_active": True,
        "id": users["assignee"],
        "first_name": "Planning",
        "last_name": "User",
    }

    for value in ("low", "normal", "major", "critical"):
        changed = await client.patch(
            f"/api/tasks/{task_body['id']}",
            json={"priority": value},
            headers=owner if value in {"low", "normal"} else assignee,
        )
        assert changed.status_code == 200
        assert changed.json()["priority"] == value

    for value in ("urgent", "", "Low", 1, {}):
        invalid = await client.patch(
            f"/api/tasks/{task_body['id']}",
            json={"priority": value},
            headers=owner,
        )
        assert invalid.status_code == 422

    forbidden = await client.patch(
        f"/api/tasks/{task_body['id']}",
        json={"priority": "low"},
        headers=regular,
    )
    assert forbidden.status_code == 403

    cleared = await client.patch(
        f"/api/tasks/{task_body['id']}",
        json={"priority": None},
        headers=owner,
    )
    assert cleared.status_code == 200
    assert cleared.json()["priority"] is None

    reporter_changed = await client.patch(
        f"/api/tasks/{task_body['id']}",
        json={"reporter_id": users["regular"]},
        headers=owner,
    )
    assert reporter_changed.status_code == 200
    reporter_priority = await client.patch(
        f"/api/tasks/{task_body['id']}",
        json={"priority": "low"},
        headers=regular,
    )
    assert reporter_priority.status_code == 200
    assert reporter_priority.json()["priority"] == "low"

    unchanged = await client.patch(
        f"/api/tasks/{task_body['id']}",
        json={"description": "Priority remains"},
        headers=regular,
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["priority"] == "low"

    board = await client.get(f"/api/projects/{project['id']}/board", headers=owner)
    board_task = next(
        item
        for column in board.json()["columns"]
        for item in column["tasks"]
        if item["id"] == task_body["id"]
    )
    assert board_task["priority"] == "low"
    assert board_task["reporter"]["first_name"] == "Planning"

    page = await client.get(
        f"/api/projects/{project['id']}/board/columns/{status['id']}/tasks?limit=500",
        headers=owner,
    )
    page_task = next(item for item in page.json()["tasks"] if item["id"] == task_body["id"])
    assert page_task["priority"] == "low"
    assert page_task["assignee"]["last_name"] == "User"

    watched = await client.post(
        f"/api/tasks/{task_body['id']}/watchers",
        json={"user_id": users["assignee"]},
        headers=owner,
    )
    assert watched.status_code == 200
    assert watched.json() == [
        {
            "is_active": True,
            "id": users["assignee"],
            "first_name": "Planning",
            "last_name": "User",
        }
    ]
    assert "email" not in watched.json()[0]

    history = await client.get(f"/api/tasks/{task_body['id']}/history", headers=owner)
    entries = [
        entry for entry in history.json()["entries"] if entry["event_type"] == "priority_changed"
    ]
    assert [(entry["old_value"], entry["new_value"]) for entry in entries] == [
        (None, "low"),
        ("critical", None),
        ("major", "critical"),
        ("normal", "major"),
        ("low", "normal"),
        (None, "low"),
    ]
    notifications = await client.get("/api/notifications", headers=assignee)
    assert all(item["event_type"] != "priority_changed" for item in notifications.json())
