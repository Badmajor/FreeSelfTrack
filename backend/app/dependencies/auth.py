from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.models import User
from app.repositories.domain import DomainRepository

bearer_scheme = HTTPBearer(auto_error=False)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise authentication_error()
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().auth_secret_key, algorithms=["HS256"]
        )
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError, jwt.InvalidTokenError) as exc:
        raise authentication_error() from exc

    user = await DomainRepository(session).get_user(user_id)
    if user is None or not user.is_active:
        raise authentication_error()
    return user


async def current_user_id(user: User = Depends(current_user)) -> UUID:
    return user.id
