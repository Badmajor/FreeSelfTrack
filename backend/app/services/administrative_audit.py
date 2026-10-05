from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import request_id
from app.models.administrative_audit import AdministrativeAuditEvent
from app.repositories.administrative_audit import AdministrativeAuditRepository
from app.schemas.administrative_audit import AdministrativeAuditWrite


class AdministrativeAuditService:
    """Record successful changes inside the caller's authorized mutation transaction.

    Reuse this instance (or its server-generated operation_id) for a cascade. Producers
    supply actual before/after values once per entity/subject, after domain validation.
    Do not call for failures, reads, password/email changes or implicit deactivations.
    This writer neither grants authorization nor commits the originating transaction.
    """

    def __init__(self, session: AsyncSession, *, operation_id: UUID | None = None) -> None:
        self.repository = AdministrativeAuditRepository(session)
        self.operation_id = operation_id or request_id.get() or uuid4()

    def record(self, data: AdministrativeAuditWrite) -> AdministrativeAuditEvent | None:
        changes = [change for change in data.changes if change.old != change.new]
        if not changes:
            return None
        event = AdministrativeAuditEvent(
            operation_id=self.operation_id,
            actor_kind=data.actor_kind,
            actor_id=data.actor_id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            action=data.action,
            subject_user_id=data.subject_user_id,
            changes=[change.model_dump(mode="json") for change in changes],
        )
        self.repository.add(event)
        return event
