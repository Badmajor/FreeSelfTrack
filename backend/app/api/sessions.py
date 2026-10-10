from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import translate_errors
from app.db.session import get_session
from app.dependencies.auth import current_auth, password_change_user
from app.dependencies.auth_protection import auth_client_address, auth_limiter
from app.dependencies.session_cookie import (
    REFRESH_COOKIE,
    clear_refresh_cookie,
    csrf_protection,
    set_refresh_cookie,
)
from app.models import User
from app.models.auth_session import AuthSession
from app.schemas.domain import LoginResponse
from app.schemas.sessions import (
    PasswordChange,
)
from app.services.auth import AuthService
from app.services.auth_protection import AuthLimiter
from app.services.sessions import SessionService

router = APIRouter(prefix="/auth", tags=["sessions"])


@router.post("/refresh", response_model=LoginResponse, dependencies=[Depends(csrf_protection)])
async def refresh(
    response: Response,
    credential: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    access, new_refresh, user = await translate_errors(SessionService(session).refresh)(
        credential or ""
    )
    set_refresh_cookie(response, new_refresh)
    return LoginResponse(access_token=access, user=user)


@router.post("/logout", status_code=204, dependencies=[Depends(csrf_protection)])
async def logout(
    response: Response,
    credential: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    session: AsyncSession = Depends(get_session),
) -> None:
    await translate_errors(SessionService(session).logout)(credential or "")
    clear_refresh_cookie(response)


@router.delete("/sessions/current", status_code=204)
async def revoke_current(
    response: Response,
    auth: tuple[User, AuthSession] = Depends(current_auth),
    session: AsyncSession = Depends(get_session),
) -> None:
    await translate_errors(SessionService(session).revoke_current)(auth[0].id, auth[1].id)
    clear_refresh_cookie(response)


@router.post("/password/change", status_code=204)
async def change_password(
    data: PasswordChange,
    response: Response,
    user: User = Depends(password_change_user),
    session: AsyncSession = Depends(get_session),
    limiter: AuthLimiter = Depends(auth_limiter),
    address: str = Depends(auth_client_address),
) -> None:
    await translate_errors(limiter.check)("login", user.email, address)
    await translate_errors(AuthService(session).change_password)(
        user.id, data.current_password, data.new_password
    )
    clear_refresh_cookie(response)
