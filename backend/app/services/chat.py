import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.object_storage import PREFIX, ObjectStorage, get_storage
from app.models import Attachment, Comment, CommentMention, Task
from app.repositories.chat import ChatRepository
from app.repositories.domain import DomainRepository
from app.schemas.chat import AttachmentResponse, CommentCreate, CommentPage, CommentResponse
from app.schemas.domain import ProfileResponse
from app.services.attachment_files import MAX_FILE_SIZE, MAX_FILES, Uploaded, inspect_file
from app.services.domain import DomainService
from app.services.errors import ConflictError, InvalidWorkflowError, NotFoundError


class ChatService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage | None = None):
        self.storage = storage
        self.session = session
        self.repository = ChatRepository(session)
        self.domain = DomainService(session)
        self.users = DomainRepository(session)

    async def authorize(self, user_id: UUID, task_id: UUID) -> Task:
        task = await self.domain.get_task(user_id, task_id)
        project = await self.domain.get_project_for_read(user_id, task.project_id)
        await self.domain.get_organization(user_id, project.organization_id)
        return task

    @staticmethod
    def response(comment: Comment) -> CommentResponse:
        return CommentResponse(
            id=comment.id,
            task_id=comment.task_id,
            sequence=comment.sequence,
            author=ProfileResponse.model_validate(comment.author.profile),
            text=comment.text,
            mentions=[
                ProfileResponse.model_validate(item.user.profile) for item in comment.mentions
            ],
            attachments=[AttachmentResponse.model_validate(item) for item in comment.attachments],
            created_at=comment.created_at,
        )

    async def page(
        self, user_id: UUID, task_id: UUID, limit: int, before: int | None, after: int | None
    ) -> CommentPage:
        await self.authorize(user_id, task_id)
        if before is not None and after is not None:
            raise InvalidWorkflowError("Use either before or after")
        rows = await self.repository.page(task_id, limit, before, after)
        has_more = len(rows) > limit
        rows = rows[:limit]
        if after is None:
            rows.reverse()
        return CommentPage(comments=[self.response(row) for row in rows], has_more=has_more)

    async def get(self, user_id: UUID, task_id: UUID, comment_id: UUID) -> CommentResponse:
        await self.authorize(user_id, task_id)
        row = await self.repository.get(task_id, comment_id)
        if row is None:
            raise NotFoundError("Message not found")
        return self.response(row)

    async def prepare(self, files: list[UploadFile]) -> list[Uploaded]:
        if len(files) > MAX_FILES:
            raise InvalidWorkflowError("At most 5 files per message")
        return [
            await run_in_threadpool(inspect_file, file.filename or "file", file.file)
            for file in files
        ]

    async def create(
        self, user_id: UUID, task_id: UUID, data: CommentCreate, files: list[Uploaded]
    ) -> CommentResponse:
        task = await self.authorize(user_id, task_id)
        if (not data.text.strip() and not files) or len(files) > MAX_FILES:
            raise InvalidWorkflowError("Write a message or attach up to 5 files")
        if any(item.size > MAX_FILE_SIZE for item in files):
            raise InvalidWorkflowError("File exceeds 25 MB")
        mention_ids = set(data.mention_ids)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "text": data.text,
                    "mentions": sorted(map(str, mention_ids)),
                    "files": [(item.original_filename, item.sha256) for item in files],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        # Serialize sequence allocation and idempotent retries for this task until commit.
        await self.repository.lock(task_id)
        existing = await self.repository.existing(task_id, user_id, data.request_id)
        if existing:
            if existing.fingerprint != fingerprint:
                raise ConflictError("Request ID already used for another message")
            return self.response(existing)
        project = await self.domain.get_project_for_read(user_id, task.project_id)
        organization_members = await self.users.list_organization_members(project.organization_id)
        allowed = {member.id for member in organization_members if member.is_active}
        if not mention_ids.issubset(allowed):
            raise InvalidWorkflowError("Mentioned users must be active organization members")
        row = Comment(
            task_id=task_id,
            author_id=user_id,
            request_id=data.request_id,
            fingerprint=fingerprint,
            text=data.text,
            sequence=await self.repository.next_sequence(task_id),
        )
        self.session.add(row)
        await self.session.flush()
        for mentioned in mention_ids:
            self.session.add(CommentMention(comment_id=row.id, user_id=mentioned))
        if files:
            await self.repository.storage_lock()
        for position, item in enumerate(files):
            key = PREFIX + str(uuid4())
            await run_in_threadpool(
                (self.storage or get_storage()).put, key, item.stream, item.size
            )
            self.session.add(
                Attachment(
                    comment_id=row.id,
                    position=position,
                    filename=item.filename,
                    size=item.size,
                    object_key=key,
                    sha256=item.sha256,
                    state="pending",
                    media_type=item.media_type,
                )
            )
        recipients = (
            mention_ids
            | {task.reporter_id, task.assignee_id}
            | set(await self.users.list_task_watcher_ids(task_id))
        ) & allowed
        for recipient in recipients - {user_id}:
            if recipient is None:
                continue
            self.users.add_notification(
                recipient_id=recipient,
                task_id=task_id,
                event_type="comment_created",
                message=f"New message in {task.slug}",
                event_data=json.dumps(
                    {"comment_id": str(row.id), "project_id": str(task.project_id)}
                ),
            )
        await self.session.commit()
        return await self.get(user_id, task_id, row.id)

    async def attachment(self, user_id: UUID, attachment_id: UUID) -> Attachment:
        task_id = await self.repository.attachment_task(attachment_id)
        if task_id is None:
            raise NotFoundError("Attachment not found")
        await self.authorize(user_id, task_id)
        file = await self.repository.attachment(attachment_id)
        if file is None or file.state != "ready":
            raise NotFoundError("Attachment not found")
        return file
