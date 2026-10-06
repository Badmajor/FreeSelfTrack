from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User
from app.models.auth_session import AuthSession, PasswordReset, RefreshCredential


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_user(self, user_id: UUID) -> User | None:
        return await self.session.scalar(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.profile))
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_session(self, session_id: UUID) -> AuthSession | None:
        return await self.session.get(AuthSession, session_id, populate_existing=True)

    async def get_refresh(self, digest: str) -> RefreshCredential | None:
        return await self.session.get(RefreshCredential, digest, populate_existing=True)

    async def revoke_all(self, user_id: UUID, now: datetime) -> list[UUID]:
        revoked = await self.session.scalars(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(AuthSession.id)
        )
        await self.session.execute(delete(PasswordReset).where(PasswordReset.user_id == user_id))
        return list(revoked)

    async def get_reset(self, reset_id: UUID) -> PasswordReset | None:
        return await self.session.get(PasswordReset, reset_id, populate_existing=True)

    async def consume_reset(self, reset_id: UUID, now: datetime) -> bool:
        return (
            await self.session.scalar(
                delete(PasswordReset)
                .where(PasswordReset.id == reset_id, PasswordReset.expires_at > now)
                .returning(PasswordReset.id)
                .execution_options(synchronize_session=False)
            )
            is not None
        )

    async def next_reset_mail(self, now: datetime) -> PasswordReset | None:
        return await self.session.scalar(
            select(PasswordReset)
            .where(
                PasswordReset.sent_at.is_(None),
                PasswordReset.expires_at > now,
                PasswordReset.next_attempt_at <= now,
            )
            .order_by(PasswordReset.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    async def clean_expired(self, now: datetime) -> None:
        for model in (PasswordReset, AuthSession):
            ids = select(model.id).where(model.expires_at <= now).limit(500)
            await self.session.execute(delete(model).where(model.id.in_(ids)))
