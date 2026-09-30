import asyncio
import logging

from app.core.config import get_settings
from app.db.session import SessionFactory
from app.services.deadlines import DeadlineService

logger = logging.getLogger(__name__)


async def process_all_due() -> int:
    total = 0
    while True:
        async with SessionFactory() as session:
            processed = await DeadlineService(session).process_due()
        total += processed
        if processed < 500:
            return total


async def run() -> None:
    interval = max(1, get_settings().deadline_worker_interval_seconds)
    while True:
        try:
            processed = await process_all_due()
            if processed:
                logger.info("Created %s deadline notifications", processed)
        except Exception:
            logger.exception("Deadline notification pass failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
