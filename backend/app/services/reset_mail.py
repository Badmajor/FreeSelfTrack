import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models.auth_session import PasswordReset
from app.repositories.sessions import SessionRepository
from app.services.registration_mail import send_message
from app.services.sessions import reset_token

logger = logging.getLogger("security.auth")


def send_reset(pending: PasswordReset) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = pending.email
    message["Subject"] = "Reset your FreeSelfTrack password"
    link = settings.public_app_url + "/#reset=" + reset_token(pending.id)
    message.set_content(
        "If you requested a password reset, open this link. Otherwise ignore it.\n\n"
        + link
        + "\n\nExpires at "
        + pending.expires_at.isoformat()
        + " UTC."
    )
    send_message(message)


class ResetMailService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = SessionRepository(session)

    async def process_one(self) -> bool:
        now = datetime.now(UTC)
        pending = await self.repository.next_reset_mail(now)
        if pending is None:
            await self.repository.clean_expired(now)
            await self.session.commit()
            return False
        try:
            await run_in_threadpool(send_reset, pending)
        except (OSError, smtplib.SMTPException):
            pending.attempts += 1
            pending.next_attempt_at = now + timedelta(
                seconds=min(300, 5 * 2 ** min(pending.attempts, 6))
            )
            logger.warning("auth outcome=reset_delivery_retry")
        else:
            pending.sent_at = datetime.now(UTC)
            logger.info("auth outcome=reset_delivered")
        await self.session.commit()
        return True
