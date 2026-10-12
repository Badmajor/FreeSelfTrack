from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.administrative_audit import AdministrativeAuditEvent
from app.models.domain import UserProfile
from app.schemas.administrative_audit import EntityType

PAGE_SIZE = 20
AuditPosition = tuple[datetime, UUID]


@dataclass(frozen=True)
class AdministrativeAuditPage:
    items: list[AdministrativeAuditEvent]
    next_position: AuditPosition | None


class AdministrativeAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def actor_names(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = await self.session.scalars(select(UserProfile).where(UserProfile.user_id.in_(ids)))
        return {
            row.user_id: f"{row.first_name} {row.last_name}".strip() or str(row.user_id)
            for row in rows
        }

    def add(self, event: AdministrativeAuditEvent) -> None:
        """Join the originating transaction; never flush or commit independently."""
        self.session.add(event)

    async def page_for_entity(
        self,
        entity_type: EntityType,
        entity_id: UUID,
        *,
        after: AuditPosition | None = None,
    ) -> AdministrativeAuditPage:
        """Internal query; the read service authorizes each page before calling."""
        query = select(AdministrativeAuditEvent).where(
            AdministrativeAuditEvent.entity_type == entity_type,
            AdministrativeAuditEvent.entity_id == entity_id,
        )
        if after is not None:
            timestamp, event_id = after
            query = query.where(
                or_(
                    AdministrativeAuditEvent.occurred_at < timestamp,
                    and_(
                        AdministrativeAuditEvent.occurred_at == timestamp,
                        AdministrativeAuditEvent.id < event_id,
                    ),
                )
            )
        rows = list(
            await self.session.scalars(
                query.order_by(
                    AdministrativeAuditEvent.occurred_at.desc(), AdministrativeAuditEvent.id.desc()
                ).limit(PAGE_SIZE + 1)
            )
        )
        items = rows[:PAGE_SIZE]
        next_position = None
        if len(rows) > PAGE_SIZE:
            next_position = (items[-1].occurred_at, items[-1].id)
        return AdministrativeAuditPage(items, next_position)
