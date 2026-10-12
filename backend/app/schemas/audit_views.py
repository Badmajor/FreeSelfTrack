"""Public, read-only administrative audit contract."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.schemas.administrative_audit import AuditAction, AuditField, EntityType


class AuditQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)


class AuditActor(BaseModel):
    kind: Literal["user", "bootstrap"]
    id: UUID | None
    display_name: str


class AuditEntity(BaseModel):
    type: EntityType
    id: UUID


class AuditChangeResponse(BaseModel):
    field: AuditField
    old: JsonValue
    new: JsonValue


class AuditEntry(BaseModel):
    id: UUID
    occurred_at: datetime
    operation_id: UUID
    actor: AuditActor
    entity: AuditEntity
    action: AuditAction
    subject_user_id: UUID | None
    changes: list[AuditChangeResponse]


class AdministrativeAuditPage(BaseModel):
    items: list[AuditEntry]
    page_size: Literal[20] = 20
    next_cursor: str | None
