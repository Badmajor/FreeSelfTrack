from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    first_name: str
    last_name: str


class ProfileUpdate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    profile: ProfileResponse


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    deleted_at: datetime | None = None


class MembershipRequest(BaseModel):
    email: EmailStr


class ConfirmRequest(BaseModel):
    confirm: bool


class ProjectCreate(BaseModel):
    organization_id: UUID
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    owner_id: UUID
    name: str
    deleted_at: datetime | None = None


class StatusCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    position: int | None = Field(default=None, ge=0)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Status name must not be blank")
        return value


class StatusUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    position: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Status name must not be blank")
        return value


class StatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    position: int
    is_active: bool


class StatusReorder(BaseModel):
    status_ids: list[UUID] = Field(min_length=1)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr


class AssigneeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    status_id: UUID
    reporter_id: UUID | None = None
    assignee_id: UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status_id: UUID | None = None
    reporter_id: UUID | None = None
    assignee_id: UUID | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status_id: UUID
    slug: str
    title: str
    description: str | None
    created_by: UUID
    reporter_id: UUID
    assignee_id: UUID | None
    assignee: AssigneeSummary | None
    watchers: list[UserSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BoardColumnResponse(BaseModel):
    status: StatusResponse
    tasks: list[TaskResponse]
    next_cursor: str | None = None


class BoardResponse(BaseModel):
    project_id: UUID
    columns: list[BoardColumnResponse]


class TaskPageResponse(BaseModel):
    tasks: list[TaskResponse]
    next_cursor: str | None = None


class TaskHistoryPageResponse(BaseModel):
    entries: list["TaskHistoryResponse"]
    next_cursor: str | None = None


class TaskHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    changed_by: UUID
    actor: ProfileResponse
    from_status_id: UUID | None = None
    to_status_id: UUID | None = None
    event_type: str
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    created_at: datetime


class WatcherRequest(BaseModel):
    user_id: UUID | None = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recipient_id: UUID
    task_id: UUID | None
    event_type: str
    message: str
    event_data: str | None
    created_at: datetime
    read_at: datetime | None


class UnreadCountResponse(BaseModel):
    count: int
