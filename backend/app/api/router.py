from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.schemas.domain import (
    BoardResponse,
    ConfirmRequest,
    LoginRequest,
    LoginResponse,
    MembershipRequest,
    OrganizationCreate,
    OrganizationResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    RegisterRequest,
    StatusCreate,
    StatusReorder,
    StatusResponse,
    StatusUpdate,
    TaskCreate,
    TaskHistoryPageResponse,
    TaskPageResponse,
    TaskResponse,
    TaskUpdate,
    UserResponse,
)
from app.services.auth import AuthService
from app.services.domain import DomainService
from app.services.errors import DomainError

router = APIRouter()


def service(session: AsyncSession) -> DomainService:
    return DomainService(session)


def translate_errors(operation: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return await operation(*args, **kwargs)
        except DomainError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return wrapped


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, session: AsyncSession = Depends(get_session)) -> Any:
    return await translate_errors(AuthService(session).register)(data)


@router.post("/auth/login", response_model=LoginResponse)
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session)) -> Any:
    access_token, user = await translate_errors(AuthService(session).login)(data)
    return LoginResponse(access_token=access_token, user=user)


@router.post(
    "/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    data: OrganizationCreate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).create_organization)(user_id, data)


@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations(
    user_id: UUID = Depends(current_user_id), session: AsyncSession = Depends(get_session)
) -> Any:
    return await translate_errors(service(session).list_organizations)(user_id)


@router.get("/organizations/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_organization)(user_id, organization_id)


@router.get("/organizations/{organization_id}/projects", response_model=list[ProjectResponse])
async def list_organization_projects(
    organization_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_projects)(user_id, organization_id)


@router.get("/organizations/{organization_id}/members", response_model=list[UserResponse])
async def list_organization_members(
    organization_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_organization_members)(
        user_id, organization_id
    )


@router.post("/organizations/{organization_id}/members", response_model=UserResponse)
async def add_organization_member(
    organization_id: UUID,
    data: MembershipRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).add_organization_member)(
        user_id, organization_id, data
    )


@router.delete("/organizations/{organization_id}/members/{member_id}", response_model=UserResponse)
async def remove_organization_member(
    organization_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).remove_organization_member)(
        user_id, organization_id, member_id
    )


@router.post(
    "/organizations/{organization_id}/transfer-ownership", response_model=OrganizationResponse
)
async def transfer_organization_ownership(
    organization_id: UUID,
    data: MembershipRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).transfer_organization_ownership)(
        user_id, organization_id, data
    )


@router.delete("/organizations/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    organization_id: UUID,
    data: ConfirmRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await translate_errors(service(session).delete_organization)(user_id, organization_id, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/organizations/{organization_id}/restore", response_model=OrganizationResponse)
async def restore_organization(
    organization_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).restore_organization)(user_id, organization_id)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).create_project)(user_id, data)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_project)(user_id, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).update_project)(user_id, project_id, data)


@router.get("/projects/{project_id}/members", response_model=list[UserResponse])
async def list_project_members(
    project_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).list_project_members)(user_id, project_id)


@router.post("/projects/{project_id}/members", response_model=UserResponse)
async def add_project_member(
    project_id: UUID,
    data: MembershipRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).add_project_member)(user_id, project_id, data)


@router.delete("/projects/{project_id}/members/{member_id}", response_model=UserResponse)
async def remove_project_member(
    project_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).remove_project_member)(
        user_id, project_id, member_id
    )


@router.post("/projects/{project_id}/transfer-ownership", response_model=ProjectResponse)
async def transfer_project_ownership(
    project_id: UUID,
    data: MembershipRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).transfer_project_ownership)(
        user_id, project_id, data
    )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    data: ConfirmRequest,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await translate_errors(service(session).delete_project)(user_id, project_id, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).restore_project)(user_id, project_id)


@router.get("/projects/{project_id}/board", response_model=BoardResponse)
async def get_board(
    project_id: UUID,
    limit: int = Query(default=500, ge=1, le=500),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_board)(user_id, project_id, limit)


@router.get(
    "/projects/{project_id}/board/columns/{status_id}/tasks", response_model=TaskPageResponse
)
async def get_column_tasks(
    project_id: UUID,
    status_id: UUID,
    limit: int = Query(default=500, ge=1, le=500),
    cursor: str | None = None,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_column_tasks)(
        user_id, project_id, status_id, limit, cursor
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
    return await translate_errors(service(session).create_task)(user_id, project_id, data)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).get_task)(user_id, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    data: TaskUpdate,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(service(session).update_task)(user_id, task_id, data)


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
