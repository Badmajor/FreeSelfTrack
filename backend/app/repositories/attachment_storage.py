"""Maintenance queries, including bounded reads of the transitional bytea column."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attachment


class AttachmentStorageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def legacy_next(self) -> Attachment | None:
        return await self.session.scalar(
            select(Attachment)
            .where(Attachment.object_key.is_(None))
            .order_by(Attachment.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    async def legacy_chunk(self, attachment_id: UUID, offset: int, length: int) -> bytes:
        value = await self.session.scalar(
            text(
                "SELECT substring(content from :offset for :length) FROM attachments WHERE id = :id"
            ),
            {"id": attachment_id, "offset": offset + 1, "length": length},
        )
        if value is None:
            raise ValueError("Legacy attachment bytes missing")
        return bytes(value)

    async def locked(self, attachment_id: UUID) -> Attachment | None:
        return await self.session.scalar(
            select(Attachment).where(Attachment.id == attachment_id).with_for_update()
        )

    async def pending(self, limit: int) -> list[Attachment]:
        return list(
            await self.session.scalars(
                select(Attachment)
                .where(Attachment.state == "pending")
                .order_by(Attachment.id)
                .limit(limit)
            )
        )
