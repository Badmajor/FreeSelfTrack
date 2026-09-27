from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.schemas.domain import (
    LoginRequest,
    LoginResponse,
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
