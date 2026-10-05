"""Internal producer contract, not an HTTP input schema or an authorization grant."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityType = Literal["user", "organization", "project", "task"]
AuditAction = Literal[
    "user_created",
    "profile_updated",
    "user_blocked",
    "user_unblocked",
    "system_role_changed",
    "created",
    "updated",
    "workflow_changed",
    "member_added",
    "member_removed",
    "member_role_changed",
    "archived",
    "restored",
]
AuditField = Literal[
    "first_name",
    "last_name",
    "name",
    "description",
    "is_active",
    "is_system_admin",
    "organization_id",
    "project_id",
    "role",
    "state",
    "archived_at",
    "statuses",
]


class AuditSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class WorkflowStatusSnapshot(AuditSchema):
    id: UUID
    name: str = Field(max_length=120)
    position: int = Field(ge=0)
    is_active: bool
    is_completed: bool


class AuditChange(AuditSchema):
    field: AuditField
    old: str | bool | int | UUID | datetime | tuple[WorkflowStatusSnapshot, ...] | None
    new: str | bool | int | UUID | datetime | tuple[WorkflowStatusSnapshot, ...] | None

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        for value in (self.old, self.new):
            if value is None:
                continue
            valid = False
            if self.field in {"first_name", "last_name", "name", "description"}:
                valid = isinstance(value, str)
                maximum = {"first_name": 100, "last_name": 100, "name": 200}.get(self.field)
                if maximum is not None and isinstance(value, str):
                    valid = len(value) <= maximum
            elif self.field in {"is_active", "is_system_admin"}:
                valid = type(value) is bool
            elif self.field in {"organization_id", "project_id"}:
                valid = isinstance(value, UUID)
            elif self.field == "role":
                valid = isinstance(value, str) and value in {"member", "manager"}
            elif self.field == "state":
                valid = isinstance(value, str) and value in {"active", "archived", "revoked"}
            elif self.field == "archived_at":
                valid = isinstance(value, datetime) and value.utcoffset() is not None
            elif self.field == "statuses":
                valid = isinstance(value, tuple) and len({item.id for item in value}) == len(value)
            if not valid:
                raise ValueError("Invalid value for administrative audit field")
        return self


MEMBERSHIP_FIELDS = frozenset({"organization_id", "project_id", "role", "state"})
POLICIES: dict[tuple[str, str], frozenset[str]] = {
    ("user", "user_created"): frozenset({"first_name", "last_name", "is_active", "is_system_admin"})
    | MEMBERSHIP_FIELDS,
    ("user", "profile_updated"): frozenset({"first_name", "last_name"}),
    ("user", "user_blocked"): frozenset({"is_active"}),
    ("user", "user_unblocked"): frozenset({"is_active"}),
    ("user", "system_role_changed"): frozenset({"is_system_admin"}),
    ("project", "workflow_changed"): frozenset({"statuses"}),
}
for entity in ("organization", "project"):
    for action in ("created", "updated"):
        POLICIES[entity, action] = frozenset({"name", "description"})
for entity in ("organization", "project", "task"):
    for action in ("archived", "restored"):
        POLICIES[entity, action] = frozenset({"archived_at"})
for entity in ("user", "organization", "project"):
    for action in ("member_added", "member_removed", "member_role_changed"):
        POLICIES[entity, action] = MEMBERSHIP_FIELDS


class AdministrativeAuditWrite(AuditSchema):
    actor_kind: Literal["user", "bootstrap"] = "user"
    actor_id: UUID | None
    entity_type: EntityType
    entity_id: UUID
    action: AuditAction
    subject_user_id: UUID | None = None
    changes: tuple[AuditChange, ...]

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if (self.actor_kind == "user") != (self.actor_id is not None):
            raise ValueError("Administrative audit actor does not match its kind")
        allowed = POLICIES.get((self.entity_type, self.action))
        if allowed is None or any(change.field not in allowed for change in self.changes):
            raise ValueError("Unsupported administrative audit action or fields")
        if len({change.field for change in self.changes}) != len(self.changes):
            raise ValueError("Combine changes to a field before recording an audit event")
        membership = self.action in {"member_added", "member_removed", "member_role_changed"}
        if membership != (self.subject_user_id is not None):
            raise ValueError("Membership audit requires a subject user, other actions do not")
        if membership and self.entity_type == "user" and self.subject_user_id != self.entity_id:
            raise ValueError("Membership audit user and subject must match")
        return self
