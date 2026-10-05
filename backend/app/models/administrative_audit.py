from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdministrativeAuditEvent(Base):
    __tablename__ = "administrative_audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    operation_id: Mapped[UUID]
    actor_kind: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[UUID | None]
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(32))
    subject_user_id: Mapped[UUID | None]
    changes: Mapped[list[dict[str, object]]] = mapped_column(JSON)

    # Snapshot IDs deliberately have no foreign keys: subject cleanup must not erase history.
    __table_args__ = (
        CheckConstraint(
            "(actor_kind = 'user' AND actor_id IS NOT NULL) OR "
            "(actor_kind = 'bootstrap' AND actor_id IS NULL)",
            name="ck_administrative_audit_actor",
        ),
        CheckConstraint(
            "entity_type IN ('user', 'organization', 'project', 'task')",
            name="ck_administrative_audit_entity",
        ),
        CheckConstraint(
            "action IN ('user_created', 'profile_updated', 'user_blocked', 'user_unblocked', "
            "'system_role_changed', 'created', 'updated', 'workflow_changed', 'member_added', "
            "'member_removed', 'member_role_changed', 'archived', 'restored')",
            name="ck_administrative_audit_action",
        ),
        Index(
            "ix_administrative_audit_entity_time",
            "entity_type",
            "entity_id",
            "occurred_at",
            "id",
        ),
    )
