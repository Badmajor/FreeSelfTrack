from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import translate_errors
from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.schemas.domain import ProfileResponse, ProfileUpdate, UserResponse
from app.schemas.user_cards import (
    EmailChangeAccepted,
    EmailChangeConfirmation,
    EmailChangeInput,
    UserMembershipPage,
)
from app.schemas.user_lifecycle import (
    AdministrativeUserCreate,
    BlockUserRequest,
    EmptyRequest,
    TemporaryPasswordResponse,
    UserCard,
    UserPage,
)
from app.services.auth import AuthService
from app.services.email_change import EmailChangeService
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


@router.get("/users/{user_id}", response_model=UserCard)
async def user_card(
    user_id: UUID,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> UserCard:
    return await UserLifecycleService(session).get_card(actor_id, user_id)


@router.get("/users/{user_id}/organizations", response_model=UserMembershipPage)
async def user_organizations(
    user_id: UUID,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=50, ge=1, le=100),
) -> UserMembershipPage:
    return await UserLifecycleService(session).user_memberships(
        actor_id, user_id, "organizations", cursor, limit
    )


@router.get("/users/{user_id}/projects", response_model=UserMembershipPage)
async def user_projects(
    user_id: UUID,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=50, ge=1, le=100),
) -> UserMembershipPage:
    return await UserLifecycleService(session).user_memberships(
        actor_id, user_id, "projects", cursor, limit
    )


@router.patch("/users/{user_id}/profile", response_model=ProfileResponse)
async def user_profile_update(
    user_id: UUID,
    data: ProfileUpdate,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    return ProfileResponse.model_validate(
        await translate_errors(AuthService(session).update_profile)(actor_id, data, user_id)
    )


@router.post("/users/me/email-change", response_model=EmailChangeAccepted, status_code=202)
async def request_email_change(
    data: EmailChangeInput,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> EmailChangeAccepted:
    return EmailChangeAccepted.model_validate(
        await translate_errors(EmailChangeService(session).request)(actor_id, str(data.email))
    )


@router.post("/users/me/email-change/confirm", status_code=204)
async def confirm_email_change(
    data: EmailChangeConfirmation,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await translate_errors(EmailChangeService(session).confirm)(actor_id, data.token)
    return Response(status_code=204)


@router.patch("/users/{user_id}/email", response_model=UserResponse)
async def direct_email_change(
    user_id: UUID,
    data: EmailChangeInput,
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    result = await translate_errors(EmailChangeService(session).change_direct)(
        actor_id, user_id, str(data.email)
    )
    return UserResponse.model_validate(result)
