import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import SessionFactory
from app.services.registration_mail import RegistrationMailService
from app.services.reset_mail import ResetMailService

logger = logging.getLogger("security.auth")


async def run() -> None:
    while True:
        try:
            for service in (RegistrationMailService, ResetMailService):
                for _ in range(100):
                    async with SessionFactory() as session:
                        if not await service(session).process_one():
                            break
        except SQLAlchemyError:
            # SQL parameters may contain credentials. Record only a sanitized outcome.
            logger.error("auth outcome=mail_database_unavailable")
        await asyncio.sleep(get_settings().mail_worker_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
