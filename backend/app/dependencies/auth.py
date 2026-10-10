from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import User
from app.models.auth_session import AuthSession
from app.services.errors import AdministrativeError, InvalidCredentialsError
from app.services.sessions import SessionService

bearer_scheme = HTTPBearer(auto_error=False)


def authentication_error() -> AdministrativeError:
    return AdministrativeError(401, "authentication_required", "Authentication required")


async def current_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> tuple[User, AuthSession]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise authentication_error()
    try:
        auth = await SessionService(session).authenticate(credentials.credentials)
        session.info["authenticated_session_id"] = auth[1].id
        return auth
    except InvalidCredentialsError as exc:
        raise authentication_error() from exc


async def password_change_user(auth: tuple[User, AuthSession] = Depends(current_auth)) -> User:
    return auth[0]


async def current_user(auth: tuple[User, AuthSession] = Depends(current_auth)) -> User:
    if auth[0].must_change_password:
        raise AdministrativeError(403, "password_change_required", "Password change required")
    return auth[0]


async def current_user_id(user: User = Depends(current_user)) -> UUID:
    return user.id
