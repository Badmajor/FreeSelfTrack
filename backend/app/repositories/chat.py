from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Attachment, Comment, CommentMention, Task, User


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def query(self) -> Select[Comment]:
        return select(Comment).options(
            selectinload(Comment.author).selectinload(User.profile),
            selectinload(Comment.mentions)
            .selectinload(CommentMention.user)
            .selectinload(User.profile),
            selectinload(Comment.attachments),
        )

    async def lock(self, task_id: UUID) -> None:
        await self.session.scalar(select(Task.id).where(Task.id == task_id).with_for_update())

    async def existing(self, task_id: UUID, author_id: UUID, request_id: UUID) -> Comment | None:
        return await self.session.scalar(
            self.query().where(
                Comment.task_id == task_id,
                Comment.author_id == author_id,
                Comment.request_id == request_id,
            )
        )

    async def next_sequence(self, task_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.max(Comment.sequence)).where(Comment.task_id == task_id)
        )
        return (value or 0) + 1

    async def get(self, task_id: UUID, comment_id: UUID) -> Comment | None:
        return await self.session.scalar(
            self.query().where(Comment.task_id == task_id, Comment.id == comment_id)
        )

    async def page(
        self, task_id: UUID, limit: int, before: int | None, after: int | None
    ) -> list[Comment]:
        query = self.query().where(Comment.task_id == task_id)
        if before is not None:
            query = query.where(Comment.sequence < before)
        if after is not None:
            query = query.where(Comment.sequence > after).order_by(Comment.sequence)
        else:
            query = query.order_by(Comment.sequence.desc())
        return list(await self.session.scalars(query.limit(limit + 1)))

    async def attachment(self, attachment_id: UUID) -> Attachment | None:
        return await self.session.scalar(select(Attachment).where(Attachment.id == attachment_id))

    async def attachment_task(self, attachment_id: UUID) -> UUID | None:
        return await self.session.scalar(
            select(Comment.task_id)
            .join(Attachment, Attachment.comment_id == Comment.id)
            .where(Attachment.id == attachment_id)
        )

    async def storage_lock(self, *, exclusive: bool = False) -> None:
        # Upload + metadata commit hold a shared lock. Cleanup takes the exclusive
        # counterpart before checking references, including uncommitted publishers.
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            from sqlalchemy import text

            name = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
            await self.session.execute(text(f"SELECT {name}(240024)"))

    async def object_referenced(self, key: str) -> bool:
        return (
            await self.session.scalar(select(Attachment.id).where(Attachment.object_key == key))
            is not None
        )
