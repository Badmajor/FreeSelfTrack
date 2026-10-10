from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import translate_errors
from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.schemas.domain import UserResponse
from app.schemas.user_lifecycle import (
    AdministrativeUserCreate,
    BlockUserRequest,
    EmptyRequest,
    TemporaryPasswordResponse,
    UserPage,
)
from app.services.user_lifecycle import UserLifecycleService

router = APIRouter(tags=["users"])


@router.post("/users", response_model=TemporaryPasswordResponse, status_code=201)
async def create_user(
    data: AdministrativeUserCreate,
    response: Response,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> TemporaryPasswordResponse:
    response.headers["Cache-Control"] = "no-store"
    return TemporaryPasswordResponse.model_validate(
        await translate_errors(UserLifecycleService(session).create)(actor_id, data)
    )


@router.post(
    "/organizations/{organization_id}/users",
    response_model=TemporaryPasswordResponse,
    status_code=201,
)
async def create_organization_user(
    organization_id: UUID,
    data: AdministrativeUserCreate,
    response: Response,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> TemporaryPasswordResponse:
    response.headers["Cache-Control"] = "no-store"
    return TemporaryPasswordResponse.model_validate(
        await translate_errors(UserLifecycleService(session).create)(
            actor_id, data, organization_id
        )
    )


@router.post("/users/{user_id}/temporary-password", response_model=TemporaryPasswordResponse)
async def reset_password(
    user_id: UUID,
    response: Response,
    data: EmptyRequest | None = Body(default=None),
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> TemporaryPasswordResponse:
    response.headers["Cache-Control"] = "no-store"
    return TemporaryPasswordResponse.model_validate(
        await translate_errors(UserLifecycleService(session).reset)(actor_id, user_id)
    )


@router.post("/users/{user_id}/block", response_model=UserResponse)
async def block_user(
    user_id: UUID,
    data: BlockUserRequest,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    result = await translate_errors(UserLifecycleService(session).set_blocked)(
        actor_id, user_id, True
    )
    return UserResponse.model_validate(result)


@router.post("/users/{user_id}/unblock", response_model=UserResponse)
async def unblock_user(
    user_id: UUID,
    data: EmptyRequest | None = Body(default=None),
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    result = await translate_errors(UserLifecycleService(session).set_blocked)(
        actor_id, user_id, False
    )
    return UserResponse.model_validate(result)


@router.get("/users", response_model=UserPage)
async def list_users(
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
    q: str = Query(default="", max_length=200),
    state: Literal["all", "active", "blocked"] = "all",
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=50, ge=1, le=100),
) -> UserPage:
    return await UserLifecycleService(session).list_users(actor_id, q, state, cursor, limit)
