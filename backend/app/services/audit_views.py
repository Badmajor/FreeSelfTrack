import base64
import binascii
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.administrative_audit import AdministrativeAuditRepository
from app.schemas.administrative_audit import EntityType
from app.schemas.audit_views import (
    AdministrativeAuditPage,
    AuditEntry,
)
from app.services.domain import DomainService
from app.services.errors import AdministrativeError
from app.services.user_lifecycle import UserLifecycleService


class AuditViewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AdministrativeAuditRepository(session)

    async def page(
        self, actor_id: UUID, entity_type: EntityType, entity_id: UUID, cursor: str | None
    ) -> AdministrativeAuditPage:
        domain = DomainService(self.session)
        if entity_type == "user":
            card = await UserLifecycleService(self.session).get_card(actor_id, entity_id)
            if not card.capabilities["view_audit"]:
                raise AdministrativeError(403, "permission_denied", "User audit access denied")
        elif entity_type == "organization":
            await domain.get_organization(actor_id, entity_id)
        elif entity_type == "project":
            await domain.get_project_for_read(actor_id, entity_id)
        else:
            await domain.get_task(actor_id, entity_id)
        binding = ["audit", entity_type, str(entity_id)]
        after = None
        if cursor is not None:
            try:
                payload = json.loads(
                    base64.b64decode(
                        cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
                    )
                )
                if not isinstance(payload, list) or len(payload) != 5 or payload[:3] != binding:
                    raise ValueError
                timestamp = datetime.fromisoformat(payload[3])
                if timestamp.utcoffset() is None:
                    raise ValueError
                after = timestamp, UUID(payload[4])
            except (ValueError, TypeError, AttributeError, binascii.Error) as exc:
                raise AdministrativeError(422, "invalid_cursor", "Invalid audit cursor") from exc
        page = await self.repository.page_for_entity(entity_type, entity_id, after=after)
        names = await self.repository.actor_names(
            {row.actor_id for row in page.items if row.actor_id}
        )
        items = [
            AuditEntry.model_validate(
                {
                    "id": row.id,
                    "occurred_at": row.occurred_at.replace(tzinfo=UTC)
                    if row.occurred_at.tzinfo is None
                    else row.occurred_at,
                    "operation_id": row.operation_id,
                    "actor": {
                        "kind": row.actor_kind,
                        "id": row.actor_id,
                        "display_name": "System bootstrap"
                        if row.actor_kind == "bootstrap"
                        else names.get(row.actor_id, str(row.actor_id))
                        if row.actor_id
                        else "Unknown actor",
                    },
                    "entity": {"type": row.entity_type, "id": row.entity_id},
                    "action": row.action,
                    "subject_user_id": row.subject_user_id,
                    "changes": row.changes,
                }
            )
            for row in page.items
        ]
        next_cursor = None
        if page.next_position:
            timestamp, last_id = page.next_position
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            next_cursor = (
                base64.urlsafe_b64encode(
                    json.dumps([*binding, timestamp.isoformat(), str(last_id)]).encode()
                )
                .decode()
                .rstrip("=")
            )
        return AdministrativeAuditPage(items=items, next_cursor=next_cursor)
