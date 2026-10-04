import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from app.core.object_storage import get_storage
from app.db.session import SessionFactory
from app.services.attachment_maintenance import AttachmentMaintenance
from app.services.errors import DomainError

logger = logging.getLogger(__name__)


async def run() -> None:
    while True:
        try:
            async with SessionFactory() as session:
                removed = await AttachmentMaintenance(session, get_storage()).cleanup()
                logger.info("Attachment cleanup removed=%s", removed)
        except (DomainError, SQLAlchemyError):
            # Retry; never interpret a database/storage outage as an absent reference.
            logger.error("Attachment cleanup unavailable; retrying in 300 seconds")
        await asyncio.sleep(300)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
