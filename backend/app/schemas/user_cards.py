from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class EmailChangeConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: str = Field(min_length=1, max_length=1024, repr=False)


class EmailChangeAccepted(BaseModel):
    message: str = "Check your new email address to confirm the change."
    expires_at: datetime


class UserMembershipSummary(BaseModel):
    id: UUID
    name: str
    role: Literal["manager", "member"]
    can_open: bool
    organization_id: UUID | None = None
    organization_name: str | None = None


class UserMembershipPage(BaseModel):
    items: list[UserMembershipSummary]
    next_cursor: str | None
