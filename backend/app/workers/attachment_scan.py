import asyncio
import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.malware_scanner import get_scanner
from app.core.object_storage import get_storage
from app.db.session import SessionFactory
from app.services.attachment_scanning import AttachmentScanning
from app.services.errors import DomainError

logger = logging.getLogger(__name__)


async def run() -> None:
    # Keyset cursor advances even on transient failures: one missing object must
    # not starve newer uploads. Each pass retries unresolved pending rows.
    after: UUID | None = None
    while True:
        try:
            async with SessionFactory() as session:
                after = await AttachmentScanning(session, get_storage(), get_scanner()).scan_next(
                    after
                )
            if after is not None:
                continue
        except (DomainError, SQLAlchemyError):
            logger.error("Attachment scan worker unavailable; retrying")
        await asyncio.sleep(get_settings().attachment_scan_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
