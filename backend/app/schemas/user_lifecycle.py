from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.domain import ProfileUpdate, UserResponse


class AdministrativeUserCreate(ProfileUpdate):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class TemporaryPasswordResponse(BaseModel):
    user: UserResponse
    temporary_password: str = Field(repr=False)


class BlockUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = Field(strict=True)

    @field_validator("confirm")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Confirmation required")
        return value


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserCard(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    is_active: bool
    created_at: datetime
    capabilities: dict[str, bool]


class UserPage(BaseModel):
    items: list[UserCard]
    next_cursor: str | None
