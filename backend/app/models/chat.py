from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.domain import User


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_comment_sequence"),
        UniqueConstraint("task_id", "author_id", "request_id", name="uq_comment_request"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    request_id: Mapped[UUID]
    fingerprint: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    author: Mapped[User] = relationship()
    mentions: Mapped[list["CommentMention"]] = relationship()
    attachments: Mapped[list["Attachment"]] = relationship(order_by="Attachment.position")


class CommentMention(Base):
    __tablename__ = "comment_mentions"
    comment_id: Mapped[UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    user: Mapped[User] = relationship()


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    comment_id: Mapped[UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    position: Mapped[int] = mapped_column(Integer, default=0)
    object_key: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    __table_args__ = (
        Index("ix_attachments_state_id", "state", "id"),
        UniqueConstraint("object_key", name="uq_attachment_object_key"),
        UniqueConstraint("comment_id", "position", name="uq_attachment_position"),
        CheckConstraint("position >= 0 AND position < 5", name="ck_attachment_position"),
        CheckConstraint(
            "state IN ('pending', 'ready', 'failed', 'infected')", name="ck_attachment_state"
        ),
        CheckConstraint("size >= 0 AND size <= 26214400", name="ck_attachment_size"),
        CheckConstraint(
            "state != 'ready' OR (object_key IS NOT NULL AND sha256 IS NOT NULL)",
            name="ck_attachment_ready",
        ),
    )
