import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models.email_change import EmailChangeRequest
from app.repositories.administration import AdministrationRepository
from app.repositories.email_change import EmailChangeRepository
from app.services.email_change import email_change_token
from app.services.registration_mail import send_message

logger = logging.getLogger("security.auth")


def send_email_change(pending: EmailChangeRequest) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = pending.new_email
    message["Subject"] = "Confirm your FreeSelfTrack email change"
    link = (
        settings.public_app_url.rstrip("/")
        + "/#email-change="
        + email_change_token(pending.request_id)
    )
    message.set_content(
        "Sign in to the account that requested this change and confirm the new email address. "
        "If you did not request this change, ignore this message.\n\n"
        + link
        + "\n\nExpires at "
        + pending.expires_at.isoformat()
        + " UTC."
    )
    send_message(message)


class EmailChangeMailService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = EmailChangeRepository(session)

    async def process_one(self) -> bool:
        # Match lifecycle lock ordering; cancellation cannot race delivery/commit.
        await AdministrationRepository(self.session).lock_lifecycle(shared=True)
        now = datetime.now(UTC)
        pending = await self.repository.next_mail(now)
        if pending is None:
            await self.repository.clean_expired(now)
            await self.session.commit()
            return False
        pending.attempts += 1
        try:
            await run_in_threadpool(send_email_change, pending)
        except (OSError, smtplib.SMTPException):
            pending.next_attempt_at = now + timedelta(
                seconds=min(300, 10 * 2 ** min(pending.attempts - 1, 5))
            )
            logger.warning("auth outcome=email_change_delivery_retry")
        else:
            pending.sent_at = now
        await self.session.commit()
        return True
