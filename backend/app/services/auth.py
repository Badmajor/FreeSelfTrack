from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import User
from app.repositories.domain import DomainRepository
from app.schemas.domain import LoginRequest, RegisterRequest
from app.services.errors import DuplicateEmailError, InvalidCredentialsError

password_hash = PasswordHash.recommended()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DomainRepository(session)

    async def register(self, data: RegisterRequest) -> User:
        email = normalize_email(str(data.email))
        if await self.repository.get_user_by_email(email) is not None:
            raise DuplicateEmailError("Email is already registered")

        user = User(email=email, password_hash=password_hash.hash(data.password))
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateEmailError("Email is already registered") from exc
        return user

    async def login(self, data: LoginRequest) -> tuple[str, User]:
        email = normalize_email(str(data.email))
        user = await self.repository.get_user_by_email(email)
        if (
            user is None
            or not user.is_active
            or not password_hash.verify(data.password, user.password_hash)
        ):
            raise InvalidCredentialsError("Invalid email or password")
        return self.create_access_token(user.id), user

    @staticmethod
    def create_access_token(user_id: UUID) -> str:
        settings = get_settings()
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        }
        return jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")
