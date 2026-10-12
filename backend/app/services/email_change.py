import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import User
from app.models.email_change import EmailChangeRequest
from app.repositories.email_change import EmailChangeRepository
from app.schemas.user_cards import EmailChangeAccepted
from app.services.auth_protection import normalize_email
from app.services.errors import AdministrativeError
from app.services.sessions import token_digest
from app.services.user_lifecycle import UserLifecycleService
from app.services.verification import is_expired


def email_change_token(request_id: UUID) -> str:
    signature = hmac.new(
        get_settings().auth_secret_key.encode(),
        b"email-change-v1:" + request_id.bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"{request_id}.{signature}"


class EmailChangeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.lifecycle = UserLifecycleService(session)
        self.repository = EmailChangeRepository(session)

    @staticmethod
    def protect_admin(user: User) -> None:
        if user.is_system_admin:
            raise AdministrativeError(
                403,
                "system_admin_protected",
                "Administrator email is managed by deployment configuration",
            )

    async def check_email(self, email: str, user: User, *, request: bool = False) -> str:
        email = normalize_email(email)
        if request and email == user.email:
            raise AdministrativeError(422, "email_unchanged", "Choose a different email address")
        existing = await self.lifecycle.domain.get_user_by_email(email)
        if existing is not None and existing.id != user.id:
            raise AdministrativeError(409, "email_in_use", "Email is already in use")
        return email

    async def request(self, actor_id: UUID, email: str) -> EmailChangeAccepted:
        user = await self.lifecycle._actor(actor_id)
        self.protect_admin(user)
        email = await self.check_email(email, user, request=True)
        now = datetime.now(UTC)
        await self.repository.cancel(actor_id)
        identifier = uuid4()
        expires = now + timedelta(hours=6)
        self.session.add(
            EmailChangeRequest(
                user_id=actor_id,
                request_id=identifier,
                new_email=email,
                token_hash=token_digest(email_change_token(identifier)),
                expires_at=expires,
                next_attempt_at=now,
                attempts=0,
            )
        )
        await self.session.commit()
        return EmailChangeAccepted(expires_at=expires)

    async def apply(self, user: User, email: str) -> None:
        email = await self.check_email(email, user)
        try:
            user.email = email
            await self.repository.cancel(user.id)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            # The unique users.email constraint also protects against external concurrent writers.
            raise AdministrativeError(409, "email_in_use", "Email is already in use") from exc

    async def confirm(self, actor_id: UUID, token: str) -> None:
        user = await self.lifecycle._actor(actor_id)
        self.protect_admin(user)
        pending = await self.repository.get(actor_id)
        if (
            pending is None
            or is_expired(pending.expires_at)
            or not hmac.compare_digest(pending.token_hash, token_digest(token))
            or not hmac.compare_digest(
                token_digest(email_change_token(pending.request_id)), pending.token_hash
            )
        ):
            raise AdministrativeError(
                422, "invalid_email_token", "Invalid or expired email confirmation"
            )
        await self.apply(user, pending.new_email)

    async def change_direct(self, actor_id: UUID, target_id: UUID, email: str) -> User:
        actor = await self.lifecycle._actor(actor_id, target_id)
        if not actor.is_system_admin:
            raise AdministrativeError(403, "permission_denied", "System administrator required")
        user = await self.lifecycle.sessions.lock_user(target_id)
        if user is None:
            raise AdministrativeError(404, "not_found", "User not found")
        self.protect_admin(user)
        await self.apply(user, email)
        return user
