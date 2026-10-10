import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import SessionFactory
from app.repositories.sessions import SessionRepository

logger = logging.getLogger("security.auth")


async def run() -> None:
    while True:
        try:
            async with SessionFactory() as session:
                await SessionRepository(session).clean_expired(datetime.now(UTC))
                await session.commit()
        except SQLAlchemyError:
            # SQL parameters may contain credentials. Record only a sanitized outcome.
            logger.error("auth outcome=mail_database_unavailable")
        await asyncio.sleep(get_settings().mail_worker_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
