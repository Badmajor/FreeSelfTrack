from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import request_id
from app.models.audit import SecurityEvent


def record_event(
    session: AsyncSession,
    event_type: str,
    *,
    actor_id: UUID | None,
    target_type: str,
    target_id: UUID | None,
    organization_id: UUID | None = None,
    actor_kind: Literal[
        "user", "anonymous", "attachment_scanner", "attachment_operator", "bootstrap"
    ] = "user",
    member_id: UUID | None = None,
    previous_owner_id: UUID | None = None,
    owner_id: UUID | None = None,
    previous_state: str | None = None,
    state: str | None = None,
) -> None:
    """Append in the caller's transaction. Accept only enumerated, content-free metadata."""
    if state not in {None, "pending", "ready", "failed", "infected"} or previous_state not in {
        None,
        "pending",
        "ready",
        "failed",
        "infected",
    }:
        raise ValueError("Invalid audit attachment state")
    details = {
        key: str(value)
        for key, value in {
            "member_id": member_id,
            "previous_owner_id": previous_owner_id,
            "owner_id": owner_id,
            "previous_state": previous_state,
            "state": state,
        }.items()
        if value is not None
    }
    session.add(
        SecurityEvent(
            event_type=event_type,
            actor_id=actor_id,
            actor_kind=actor_kind,
            target_type=target_type,
            target_id=target_id,
            organization_id=organization_id,
            request_id=request_id.get() or uuid4(),
            details=details,
        )
    )
