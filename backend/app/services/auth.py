import logging
from datetime import UTC, datetime
from uuid import UUID

from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models import User
from app.repositories.administration import AdministrationRepository
from app.repositories.domain import DomainRepository
from app.repositories.sessions import SessionRepository
from app.schemas.domain import (
    LoginRequest,
    ProfileResponse,
    ProfileUpdate,
)
from app.services.audit import record_event
from app.services.auth_protection import normalize_email, validate_password
from app.services.errors import InvalidCredentialsError, NotFoundError, PermissionDeniedError
from app.services.sessions import SessionService

password_hash = PasswordHash.recommended()
logger = logging.getLogger("security.auth")


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DomainRepository(session)

    async def login(self, data: LoginRequest) -> tuple[str, str, User]:
        await AdministrationRepository(self.session).lock_lifecycle(shared=True)
        email = normalize_email(str(data.email))
        user = await self.repository.get_user_by_email(email)
        if user is not None:
            user = await SessionRepository(self.session).lock_user(user.id)
        valid = await run_in_threadpool(
            password_hash.verify,
            data.password,
            user.password_hash if user else get_settings().auth_dummy_hash,
        )
        if user is None or not user.is_active or not valid:
            record_event(
                self.session,
                "login_failed",
                actor_id=None,
                actor_kind="anonymous",
                target_type="user",
                target_id=user.id if user else None,
            )
            await self.session.commit()
            logger.info("auth outcome=credentials_invalid")
            raise InvalidCredentialsError("Invalid email or password")
        logger.info("auth outcome=login_success")
        access, refresh = await SessionService(self.session).start(user)
        return access, refresh, user

    async def get_profile(self, user_id: UUID) -> ProfileResponse:
        user = await self.repository.get_user(user_id)
        if user is None or user.profile is None:
            raise NotFoundError("User profile not found")
        return ProfileResponse.model_validate(user.profile)

    async def update_profile(self, user_id: UUID, data: ProfileUpdate) -> ProfileResponse:
        await AdministrationRepository(self.session).lock_lifecycle()
        user = await SessionRepository(self.session).lock_user(user_id)
        await SessionService(self.session).recheck_request_session(user_id)
        if user is None or not user.is_active:
            raise InvalidCredentialsError("Authentication required")
        if user.must_change_password:
            raise PermissionDeniedError("Password change required")
        if user.profile is None:
            raise NotFoundError("User profile not found")
        user.profile.first_name = data.first_name
        user.profile.last_name = data.last_name
        await self.session.commit()
        return ProfileResponse.model_validate(user.profile)

    async def confirm_password(self, user_id: UUID, password: str) -> User:
        user = await SessionRepository(self.session).lock_user(user_id)
        await SessionService(self.session).recheck_request_session(user_id)
        valid = await run_in_threadpool(
            password_hash.verify,
            password,
            user.password_hash if user else get_settings().auth_dummy_hash,
        )
        if user is None or not user.is_active or not valid:
            raise InvalidCredentialsError("Invalid email or password")
        return user

    async def _revoke_all(self, user_id: UUID) -> None:
        for session_id in await SessionRepository(self.session).revoke_all(
            user_id, datetime.now(UTC)
        ):
            record_event(
                self.session,
                "session_revoked",
                actor_id=user_id,
                target_type="session",
                target_id=session_id,
            )

    async def change_password(self, user_id: UUID, current: str, new: str) -> None:
        await AdministrationRepository(self.session).lock_lifecycle()
        user = await self.confirm_password(user_id, current)
        if user.is_system_admin:
            raise PermissionDeniedError(
                "Configuration administrator credentials are managed by bootstrap"
            )
        await validate_password(new)
        user.password_hash = await run_in_threadpool(password_hash.hash, new)
        user.must_change_password = False
        await self._revoke_all(user.id)
        await self.session.commit()
        logger.info("auth outcome=password_changed")
