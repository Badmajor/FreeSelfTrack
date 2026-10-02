import hmac
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models import User, UserProfile
from app.models.auth_session import PasswordReset
from app.models.registration import PendingRegistration
from app.repositories.domain import DomainRepository
from app.repositories.registration import RegistrationRepository
from app.repositories.sessions import SessionRepository
from app.schemas.domain import (
    LoginRequest,
    ProfileResponse,
    ProfileUpdate,
    RegisterRequest,
    VerifyEmailRequest,
)
from app.services.auth_protection import normalize_email, validate_password
from app.services.errors import ConflictError, InvalidCredentialsError, NotFoundError
from app.services.sessions import SessionService, invalid_session, reset_token, token_digest
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

    async def login(self, data: LoginRequest) -> tuple[str, str, User]:
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
        user = await self.repository.get_user(user_id)
        if user is None or user.profile is None:
            raise NotFoundError("User profile not found")
        user.profile.first_name = data.first_name
        user.profile.last_name = data.last_name
        await self.session.commit()
        return ProfileResponse.model_validate(user.profile)

    async def confirm_password(self, user_id: UUID, password: str) -> User:
        user = await SessionRepository(self.session).lock_user(user_id)
        valid = await run_in_threadpool(
            password_hash.verify,
            password,
            user.password_hash if user else get_settings().auth_dummy_hash,
        )
        if user is None or not user.is_active or not valid:
            raise InvalidCredentialsError("Invalid email or password")
        return user

    async def change_password(self, user_id: UUID, current: str, new: str) -> None:
        user = await self.confirm_password(user_id, current)
        await validate_password(new)
        user.password_hash = await run_in_threadpool(password_hash.hash, new)
        await SessionRepository(self.session).revoke_all(user.id, datetime.now(UTC))
        await self.session.commit()
        logger.info("auth outcome=password_changed")

    async def deactivate(self, user_id: UUID, password: str) -> None:
        user = await self.confirm_password(user_id, password)
        repository = SessionRepository(self.session)
        if await repository.owns_resources(user.id):
            raise ConflictError("Transfer organization and project ownership before deactivation")
        user.is_active = False
        await repository.revoke_all(user.id, datetime.now(UTC))
        await self.session.commit()
        logger.info("auth outcome=account_deactivated")

    async def request_password_reset(self, email: str) -> None:
        user = await self.repository.get_user_by_email(normalize_email(email))
        if user is not None:
            user = await SessionRepository(self.session).lock_user(user.id)
        if user is not None and user.is_active:
            now = datetime.now(UTC)
            reset_id = uuid4()
            self.session.add(
                PasswordReset(
                    id=reset_id,
                    user_id=user.id,
                    email=user.email,
                    token_hash=token_digest(reset_token(reset_id)),
                    expires_at=now + timedelta(seconds=get_settings().reset_lifetime_seconds),
                    next_attempt_at=now,
                )
            )
        await self.session.commit()
        logger.info("auth outcome=password_reset_requested")

    async def reset_password(self, token: str, new: str) -> None:
        repository = SessionRepository(self.session)
        try:
            reset_id = UUID(token.split(".")[0])
        except ValueError as exc:
            raise invalid_session() from exc
        pending = await repository.get_reset(reset_id)
        if pending is None:
            raise invalid_session()
        user = await repository.lock_user(pending.user_id)
        pending = await repository.get_reset(reset_id)
        if (
            pending is None
            or user is None
            or not user.is_active
            or not hmac.compare_digest(pending.token_hash, token_digest(token))
            or not hmac.compare_digest(token, reset_token(reset_id))
            or is_expired(pending.expires_at)
        ):
            raise invalid_session()
        await validate_password(new)
        hashed = await run_in_threadpool(password_hash.hash, new)
        if not await repository.consume_reset(reset_id, datetime.now(UTC)):
            raise invalid_session()
        user.password_hash = hashed
        await repository.revoke_all(user.id, datetime.now(UTC))
        await self.session.commit()
        logger.info("auth outcome=password_reset_completed")
