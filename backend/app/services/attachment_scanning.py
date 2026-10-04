import logging
from tempfile import TemporaryFile
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.malware_scanner import MalwareScanner, ScanUnavailable
from app.core.object_storage import ObjectStorage, StorageUnavailable
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.services.attachment_files import inspect_file
from app.services.audit import record_event
from app.services.errors import InvalidWorkflowError

logger = logging.getLogger(__name__)


class AttachmentScanning:
    def __init__(self, session: AsyncSession, storage: ObjectStorage, scanner: MalwareScanner):
        self.session, self.storage, self.scanner = session, storage, scanner
        self.repository = AttachmentStorageRepository(session)

    async def scan_next(self, after: UUID | None = None) -> UUID | None:
        row = await self.repository.next_pending(after)
        if row is None:
            await self.session.rollback()
            return None
        attachment_id = row.id
        assert row.object_key is not None
        try:
            with TemporaryFile() as source:
                size, digest = await run_in_threadpool(self.storage.copy_to, row.object_key, source)
                if size != row.size or digest != row.sha256:
                    row.state = "failed"
                else:
                    inspected = await run_in_threadpool(inspect_file, row.filename, source)
                    row.state = await run_in_threadpool(self.scanner.scan, source)
                    row.media_type = inspected.media_type
        except InvalidWorkflowError:
            row.state = "failed"
        except (ScanUnavailable, StorageUnavailable, OSError):
            await self.session.rollback()
            logger.warning("attachment_scan retry id=%s", attachment_id)
            return attachment_id
        state = row.state
        record_event(
            self.session,
            "attachment_state_changed",
            actor_id=None,
            actor_kind="attachment_scanner",
            target_type="attachment",
            target_id=row.id,
            organization_id=await self.repository.organization_id(row.id),
            previous_state="pending",
            state=state,
        )
        await self.session.commit()
        logger.info("attachment_scan id=%s state=%s", attachment_id, state)
        return attachment_id
