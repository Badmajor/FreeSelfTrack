from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.registration import PendingRegistration


class RegistrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, registration_id: UUID) -> PendingRegistration | None:
        return await self.session.get(PendingRegistration, registration_id)

    async def consume(self, registration_id: UUID, now: datetime) -> bool:
        result = await self.session.scalar(
            delete(PendingRegistration)
            .where(
                PendingRegistration.id == registration_id,
                PendingRegistration.expires_at > now,
            )
            .returning(PendingRegistration.id)
            .execution_options(synchronize_session=False)
        )
        return result is not None

    async def next_mail(self, now: datetime) -> PendingRegistration | None:
        return await self.session.scalar(
            select(PendingRegistration)
            .where(
                PendingRegistration.sent_at.is_(None),
                PendingRegistration.expires_at > now,
                PendingRegistration.next_attempt_at <= now,
            )
            .order_by(PendingRegistration.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    async def clean_expired(self, now: datetime) -> None:
        # Bounded cleanup avoids long transactions after a worker outage.
        ids = select(PendingRegistration.id).where(PendingRegistration.expires_at <= now).limit(500)
        await self.session.execute(
            delete(PendingRegistration).where(PendingRegistration.id.in_(ids))
        )
