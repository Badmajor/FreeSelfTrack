from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_change import EmailChangeRequest


class EmailChangeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: UUID) -> EmailChangeRequest | None:
        return await self.session.get(EmailChangeRequest, user_id, populate_existing=True)

    async def cancel(self, user_id: UUID) -> None:
        await self.session.execute(
            delete(EmailChangeRequest).where(EmailChangeRequest.user_id == user_id)
        )

    async def next_mail(self, now: datetime) -> EmailChangeRequest | None:
        return await self.session.scalar(
            select(EmailChangeRequest)
            .where(
                EmailChangeRequest.sent_at.is_(None),
                EmailChangeRequest.expires_at > now,
                EmailChangeRequest.next_attempt_at <= now,
            )
            .order_by(EmailChangeRequest.next_attempt_at, EmailChangeRequest.user_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    async def clean_expired(self, now: datetime) -> None:
        ids = (
            select(EmailChangeRequest.user_id)
            .where(EmailChangeRequest.expires_at <= now)
            .limit(500)
        )
        await self.session.execute(
            delete(EmailChangeRequest).where(EmailChangeRequest.user_id.in_(ids))
        )
