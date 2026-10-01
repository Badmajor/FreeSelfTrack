import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models import User, UserProfile
from app.models.registration import PendingRegistration
from app.repositories.domain import DomainRepository
from app.repositories.registration import RegistrationRepository
from app.schemas.domain import (
    LoginRequest,
    ProfileResponse,
    ProfileUpdate,
    RegisterRequest,
    VerifyEmailRequest,
)
from app.services.auth_protection import normalize_email, validate_password
from app.services.errors import InvalidCredentialsError, NotFoundError
from app.services.verification import InvalidVerificationError, is_expired, read_verification_token

password_hash = PasswordHash.recommended()
logger = logging.getLogger("security.auth")


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DomainRepository(session)

    async def register(self, data: RegisterRequest) -> None:
        await validate_password(data.password)
        now = datetime.now(UTC)
        # No account lookup: every valid submission follows the same durable mail path.
        self.session.add(
            PendingRegistration(
                email=normalize_email(str(data.email)),
                password_hash=await run_in_threadpool(password_hash.hash, data.password),
                first_name=data.first_name,
                last_name=data.last_name,
                expires_at=now + timedelta(seconds=get_settings().verification_lifetime_seconds),
                next_attempt_at=now,
            )
        )
        await self.session.commit()
        logger.info("auth outcome=registration_accepted")

    async def verify_email(self, data: VerifyEmailRequest) -> None:
        registration_id = read_verification_token(data.token)
        repository = RegistrationRepository(self.session)
        registration = await repository.get(registration_id)
        valid = await run_in_threadpool(
            password_hash.verify,
            data.password,
            registration.password_hash if registration else get_settings().auth_dummy_hash,
        )
        if registration is None or not valid or is_expired(registration.expires_at):
            logger.info("auth outcome=verification_invalid")
            raise InvalidVerificationError("Invalid or expired confirmation")
        # Snapshot before DELETE expires the ORM instance. Consumption and account creation
        # commit together; a replay/concurrent request cannot consume the same row twice.
        email, hashed = registration.email, registration.password_hash
        first_name, last_name = registration.first_name, registration.last_name
        if not await repository.consume(registration_id, datetime.now(UTC)):
            raise InvalidVerificationError("Invalid or expired confirmation")
        if await self.repository.get_user_by_email(email) is None:
            try:
                async with self.session.begin_nested():
                    self.session.add(
                        User(
                            email=email,
                            password_hash=hashed,
                            profile=UserProfile(first_name=first_name, last_name=last_name),
                        )
                    )
                    await self.session.flush()
            except IntegrityError:
                # Another confirmed submission for this email may win the unique constraint.
                if await self.repository.get_user_by_email(email) is None:
                    raise
        await self.session.commit()
        logger.info("auth outcome=verification_accepted")

    async def login(self, data: LoginRequest) -> tuple[str, User]:
        email = normalize_email(str(data.email))
        user = await self.repository.get_user_by_email(email)
        valid = await run_in_threadpool(
            password_hash.verify,
            data.password,
            user.password_hash if user else get_settings().auth_dummy_hash,
        )
        if user is None or not user.is_active or not valid:
            logger.info("auth outcome=credentials_invalid")
            raise InvalidCredentialsError("Invalid email or password")
        logger.info("auth outcome=login_success")
        return self.create_access_token(user.id), user

    async def get_profile(self, user_id: UUID) -> ProfileResponse:
        user = await self.repository.get_user(user_id)
        if user is None or user.profile is None:
            raise NotFoundError("User profile not found")
        return ProfileResponse.model_validate(user.profile)

    async def update_profile(self, user_id: UUID, data: ProfileUpdate) -> ProfileResponse:
        user = await self.repository.get_user(user_id)
        if user is None or user.profile is None:
            raise NotFoundError("User profile not found")
        user.profile.first_name = data.first_name
        user.profile.last_name = data.last_name
        await self.session.commit()
        return ProfileResponse.model_validate(user.profile)

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
