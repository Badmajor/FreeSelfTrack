from collections.abc import Awaitable, Callable
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.dependencies.auth_protection import auth_client_address, auth_limiter
from app.dependencies.session_cookie import csrf_protection, set_refresh_cookie
from app.schemas.domain import (
    BoardResponse,
    ConfirmRequest,
    LoginRequest,
    LoginResponse,
    MembershipPage,
    MembershipPut,
    MembershipResponse,
    NotificationResponse,
    OrganizationCreate,
    OrganizationPage,
    OrganizationResponse,
    OrganizationUpdate,
    ParticipantPage,
    ParticipantSummary,
    ProfileResponse,
    ProfileUpdate,
    ProjectCreate,
    ProjectPage,
    ProjectResponse,
    ProjectUpdate,
    StatusCreate,
    StatusReorder,
    StatusResponse,
    StatusUpdate,
    TaskCreate,
    TaskHistoryPageResponse,
    TaskLinkCreate,
    TaskLinkResponse,
    TaskListPage,
    TaskPageResponse,
    TaskResponse,
    TaskSearchResponse,
    TaskUpdate,
    UnreadCountResponse,
    WatcherRequest,
)
from app.services.auth import AuthService
from app.services.auth_protection import AuthLimiter, normalize_email
from app.services.domain import DomainService
from app.services.errors import AdministrativeError, DomainError
from app.services.memberships import MembershipService

router = APIRouter()


def service(session: AsyncSession) -> DomainService:
    return DomainService(session)


def translate_errors(operation: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return await operation(*args, **kwargs)
        except AdministrativeError:
            raise
        except DomainError as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=str(exc), headers=getattr(exc, "headers", None)
            ) from exc

    return wrapped


@router.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(csrf_protection)])
async def login(
    data: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    limiter: AuthLimiter = Depends(auth_limiter),
    address: str = Depends(auth_client_address),
) -> Any:
    await translate_errors(limiter.check)("login", normalize_email(str(data.email)), address)
    access_token, refresh_token, user = await translate_errors(AuthService(session).login)(data)
    set_refresh_cookie(response, refresh_token)
    return LoginResponse(access_token=access_token, user=user)


@router.get("/users/me/profile", response_model=ProfileResponse)
async def get_my_profile(
    user_id: UUID = Depends(current_user_id), session: AsyncSession = Depends(get_session)
) -> Any:
    return await translate_errors(AuthService(session).get_profile)(user_id)


@router.patch("/users/me/profile", response_model=ProfileResponse)
async def update_my_profile(
    data: ProfileUpdate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(AuthService(session).update_profile)(user_id, data)


@router.post(
    "/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    data: OrganizationCreate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).create_organization)(user_id, data)
    return await service(session).organization_response(user_id, result)


@router.patch("/organizations/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: UUID,
    data: OrganizationUpdate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> OrganizationResponse:
    result = await service(session).update_organization(user_id, organization_id, data)
    return await service(session).organization_response(user_id, result)


@router.get("/organizations", response_model=OrganizationPage)
async def list_organizations(
    state: Literal["active", "archived", "all"] = "active",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).resource_page)(
        user_id, "organization", None, state, cursor, limit
    )


@router.get("/organizations/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).get_organization)(user_id, organization_id)
    return await service(session).organization_response(user_id, result)


@router.get("/organizations/{organization_id}/projects", response_model=ProjectPage)
async def list_organization_projects(
    organization_id: UUID,
    state: Literal["active", "archived", "all"] = "active",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).resource_page)(
        user_id, "project", organization_id, state, cursor, limit
    )


@router.post("/organizations/{organization_id}/members", include_in_schema=False)
@router.post("/projects/{project_id}/members", include_in_schema=False)
async def removed_email_membership() -> None:
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/organizations/{organization_id}/members", response_model=MembershipPage)
async def list_organization_members(
    organization_id: UUID,
    state: Literal["active", "archived"] | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> MembershipPage:
    return await MembershipService(session).page(
        user_id, "organization", organization_id, state, cursor, limit
    )


@router.put(
    "/organizations/{organization_id}/members/{member_id}", response_model=MembershipResponse
)
async def put_organization_member(
    organization_id: UUID,
    member_id: UUID,
    data: MembershipPut,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> MembershipResponse:
    return await MembershipService(session).put(
        user_id, "organization", organization_id, member_id, data.role
    )


@router.delete("/organizations/{organization_id}/members/{member_id}", status_code=204)
async def remove_organization_member(
    organization_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await MembershipService(session).remove(user_id, "organization", organization_id, member_id)
    return Response(status_code=204)


@router.delete("/organizations/{organization_id}", include_in_schema=False)
async def removed_organization_delete(organization_id: UUID) -> None:
    raise HTTPException(status_code=404, detail="Not found")


@router.post("/organizations/{organization_id}/archive", response_model=OrganizationResponse)
async def archive_organization(
    organization_id: UUID,
    data: ConfirmRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).archive_organization)(
        user_id, organization_id, data
    )
    return await service(session).organization_response(user_id, result)


@router.post("/organizations/{organization_id}/restore", response_model=OrganizationResponse)
async def restore_organization(
    organization_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).restore_organization)(user_id, organization_id)
    return await service(session).organization_response(user_id, result)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).create_project)(user_id, data)
    return await service(session).project_response(user_id, result)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).get_project_for_read)(user_id, project_id)
    return await service(session).project_response(user_id, result)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).update_project)(user_id, project_id, data)
    return await service(session).project_response(user_id, result)


@router.get("/projects/{project_id}/members", response_model=MembershipPage)
async def list_project_members(
    project_id: UUID,
    state: Literal["active", "archived"] | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> MembershipPage:
    return await MembershipService(session).page(
        user_id, "project", project_id, state, cursor, limit
    )


@router.put("/projects/{project_id}/members/{member_id}", response_model=MembershipResponse)
async def put_project_member(
    project_id: UUID,
    member_id: UUID,
    data: MembershipPut,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> MembershipResponse:
    return await MembershipService(session).put(
        user_id, "project", project_id, member_id, data.role
    )


@router.delete("/projects/{project_id}/members/{member_id}", status_code=204)
async def remove_project_member(
    project_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await MembershipService(session).remove(user_id, "project", project_id, member_id)
    return Response(status_code=204)


@router.delete("/projects/{project_id}", include_in_schema=False)
async def removed_project_delete(project_id: UUID) -> None:
    raise HTTPException(status_code=404, detail="Not found")


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: UUID,
    data: ConfirmRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).archive_project)(user_id, project_id, data)
    return await service(session).project_response(user_id, result)


@router.post("/projects/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result = await translate_errors(service(session).restore_project)(user_id, project_id)
    return await service(session).project_response(user_id, result)


@router.get("/projects/{project_id}/board", response_model=BoardResponse)
async def get_board(
    project_id: UUID,
    limit: int = Query(default=500, ge=1, le=500),
    state: Literal["active", "archived", "all"] = "active",
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_board)(user_id, project_id, limit, state)


@router.get(
    "/projects/{project_id}/board/columns/{status_id}/tasks", response_model=TaskPageResponse
)
async def get_column_tasks(
    project_id: UUID,
    status_id: UUID,
    limit: int = Query(default=500, ge=1, le=500),
    cursor: str | None = None,
    state: Literal["active", "archived", "all"] = "active",
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_column_tasks)(
        user_id, project_id, status_id, limit, cursor, state
    )


@router.post(
    "/projects/{project_id}/statuses",
    response_model=StatusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_status(
    project_id: UUID,
    data: StatusCreate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).create_status)(user_id, project_id, data)


@router.get("/projects/{project_id}/statuses", response_model=list[StatusResponse])
async def list_statuses(
    project_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_statuses)(user_id, project_id)


@router.post("/projects/{project_id}/statuses/reorder", response_model=list[StatusResponse])
async def reorder_statuses(
    project_id: UUID,
    data: StatusReorder,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).reorder_statuses)(user_id, project_id, data)


@router.get("/projects/{project_id}/statuses/archive", response_model=list[StatusResponse])
async def list_archived_statuses(
    project_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_archived_statuses)(user_id, project_id)


@router.delete("/projects/{project_id}/statuses/{status_id}", response_model=StatusResponse)
async def archive_status(
    project_id: UUID,
    status_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).archive_status)(user_id, project_id, status_id)


@router.post("/projects/{project_id}/statuses/{status_id}/restore", response_model=StatusResponse)
async def restore_status(
    project_id: UUID,
    status_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).restore_status)(user_id, project_id, status_id)


@router.patch("/projects/{project_id}/statuses/{status_id}", response_model=StatusResponse)
async def update_status(
    project_id: UUID,
    status_id: UUID,
    data: StatusUpdate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).update_status)(
        user_id, project_id, status_id, data
    )


@router.post(
    "/projects/{project_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED
)
async def create_task(
    project_id: UUID,
    data: TaskCreate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).create_task_response)(user_id, project_id, data)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_task_response)(user_id, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    data: TaskUpdate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).update_task_response)(user_id, task_id, data)


@router.get("/tasks/{task_id}/history", response_model=TaskHistoryPageResponse)
async def get_task_history(
    task_id: UUID,
    limit: int = Query(default=500, ge=1, le=500),
    cursor: str | None = None,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_task_history)(
        user_id, task_id, limit, cursor
    )


@router.get("/organizations/{organization_id}/tasks/search", response_model=TaskSearchResponse)
async def search_organization_tasks(
    organization_id: UUID,
    slug: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    state: Literal["active", "archived", "all"] = "active",
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).search_organization_tasks)(
        user_id, organization_id, slug, limit, state
    )


@router.get("/tasks/{task_id}/links", response_model=list[TaskLinkResponse])
async def list_task_links(
    task_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_task_links)(user_id, task_id)


@router.post(
    "/tasks/{task_id}/links",
    response_model=TaskLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_link(
    task_id: UUID,
    data: TaskLinkCreate,
    response: Response,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    result, created = await translate_errors(service(session).create_task_link)(
        user_id, task_id, data
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return result


@router.delete("/tasks/{task_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_link(
    task_id: UUID,
    link_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await translate_errors(service(session).delete_task_link)(user_id, task_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks/{task_id}/watchers", response_model=list[ParticipantSummary])
async def list_task_watchers(
    task_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_task_watchers)(user_id, task_id)


@router.post("/tasks/{task_id}/watchers", response_model=list[ParticipantSummary])
async def add_task_watcher(
    task_id: UUID,
    data: WatcherRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).add_task_watcher)(user_id, task_id, data)


@router.delete("/tasks/{task_id}/watchers/{watcher_id}", response_model=list[ParticipantSummary])
async def remove_task_watcher(
    task_id: UUID,
    watcher_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).remove_task_watcher)(
        user_id, task_id, watcher_id
    )


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_notifications)(user_id)


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def unread_notification_count(
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).unread_notification_count)(user_id)


@router.post("/notifications/{notification_id}/open", response_model=NotificationResponse)
async def open_notification(
    notification_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).open_notification)(user_id, notification_id)


@router.get("/tasks/{task_id}/participants", response_model=ParticipantPage)
async def task_participants(
    task_id: UUID,
    kind: Literal["reporter", "assignee", "watcher", "mention"],
    q: str = Query("", max_length=200),
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).participants)(
        user_id, task_id, kind, q, cursor, limit
    )


@router.get("/projects/{project_id}/tasks", response_model=TaskListPage)
async def list_project_tasks(
    project_id: UUID,
    state: Literal["active", "archived", "all"] = "active",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).resource_page)(
        user_id, "task", project_id, state, cursor, limit
    )


@router.post("/tasks/{task_id}/archive", response_model=TaskResponse)
async def archive_task(
    task_id: UUID,
    data: ConfirmRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).task_lifecycle)(
        user_id, task_id, restore=False, data=data
    )


@router.post("/tasks/{task_id}/restore", response_model=TaskResponse)
async def restore_task(
    task_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).task_lifecycle)(user_id, task_id, restore=True)
