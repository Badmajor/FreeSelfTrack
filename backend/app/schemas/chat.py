from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.domain import ProfileResponse


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    text: str = Field(default="", max_length=10000)
    mention_ids: list[UUID] = Field(default_factory=list, max_length=50)


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    media_type: str
    size: int


class CommentResponse(BaseModel):
    id: UUID
    task_id: UUID
    sequence: int
    author: ProfileResponse
    text: str
    mentions: list[ProfileResponse]
    attachments: list[AttachmentResponse]
    created_at: datetime


class CommentPage(BaseModel):
    comments: list[CommentResponse]
    has_more: bool
