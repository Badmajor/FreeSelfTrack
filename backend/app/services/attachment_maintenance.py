import hashlib
import logging
from tempfile import TemporaryFile
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.object_storage import CHUNK_SIZE, PREFIX, ObjectStorage
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.repositories.chat import ChatRepository
from app.services.attachment_files import MAX_FILE_SIZE, inspect_file, normalized_filename
from app.services.errors import ConflictError, InvalidWorkflowError, NotFoundError

logger = logging.getLogger(__name__)


class AttachmentMaintenance:
    """Privileged operator operations; never exposed as user-facing HTTP endpoints."""

    def __init__(self, session: AsyncSession, storage: ObjectStorage):
        self.session = session
        self.storage = storage
        self.repository = AttachmentStorageRepository(session)
        self.chat = ChatRepository(session)

    async def migrate_one(self) -> bool:
        await self.chat.storage_lock()
        row = await self.repository.legacy_next()
        if row is None:
            await self.session.rollback()
            return False
        with TemporaryFile() as source, TemporaryFile() as verified:
            digest = hashlib.sha256()
            size = 0
            while chunk := await self.repository.legacy_chunk(row.id, size, CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise InvalidWorkflowError("Legacy file exceeds size limit; migration stopped")
                digest.update(chunk)
                await run_in_threadpool(source.write, chunk)
            if size != row.size:
                raise ConflictError("Legacy attachment size mismatch; migration stopped")
            state = "pending"
            kind = "application/octet-stream"
            try:
                inspected = await run_in_threadpool(inspect_file, row.filename, source)
                kind = inspected.media_type
            except InvalidWorkflowError:
                state = "failed"  # Preserve invalid legacy bytes without making them downloadable.
            key = PREFIX + str(uuid4())
            await run_in_threadpool(self.storage.put, key, source, size)
            actual_size, actual_hash = await run_in_threadpool(self.storage.copy_to, key, verified)
            if actual_size != size or actual_hash != digest.hexdigest():
                raise ConflictError("Object verification failed; legacy bytes retained")
            row.object_key = key
            row.sha256 = actual_hash
            row.filename = normalized_filename(row.filename)
            row.media_type = kind
            row.state = state
            await self.session.commit()
            return True

    async def review(self, attachment_id: UUID, sha256: str, state: str) -> None:
        if state not in {"ready", "failed", "infected"}:
            raise InvalidWorkflowError("Invalid review state")
        row = await self.repository.locked(attachment_id)
        if row is None or row.object_key is None:
            raise NotFoundError("Attachment not found or not migrated")
        if row.sha256 != sha256:
            raise ConflictError("Review checksum does not match attachment")
        if state == "ready":
            if row.state not in {"pending", "ready"}:
                raise ConflictError("Rejected attachments cannot be released")
            with TemporaryFile() as verified:
                size, digest = await run_in_threadpool(
                    self.storage.copy_to, row.object_key, verified
                )
                if size != row.size or digest != sha256:
                    raise ConflictError("Object verification failed")
                inspected = await run_in_threadpool(inspect_file, row.filename, verified)
                row.media_type = inspected.media_type
        row.state = state
        await self.session.commit()
        logger.warning("attachment_review id=%s state=%s sha256=%s", attachment_id, state, sha256)

    async def cleanup(self) -> int:
        await self.chat.storage_lock(exclusive=True)
        await run_in_threadpool(self.storage.abort_abandoned_parts)
        await self.session.commit()
        count = 0
        keys = self.storage.keys()
        while (key := await run_in_threadpool(next, keys, None)) is not None:
            # A publisher's shared transaction lock lasts through upload and commit.
            # Never delete on an error checking references, regardless of object age.
            await self.chat.storage_lock(exclusive=True)
            if not await self.chat.object_referenced(key):
                await run_in_threadpool(self.storage.delete, key)
                count += 1
            await self.session.commit()
        return count
