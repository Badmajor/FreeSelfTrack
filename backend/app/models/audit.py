from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[UUID | None]
    actor_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[UUID | None]
    target_type: Mapped[str] = mapped_column(String(32))
    organization_id: Mapped[UUID | None]
    request_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    details: Mapped[dict[str, str | None]] = mapped_column(JSON)

    # Snapshot identifiers intentionally have no cascading foreign keys.
    __table_args__ = (
        Index("ix_security_events_organization_created", "organization_id", "created_at", "id"),
    )
