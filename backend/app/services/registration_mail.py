import logging
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models.registration import PendingRegistration
from app.repositories.registration import RegistrationRepository
from app.services.verification import create_verification_token

logger = logging.getLogger("security.auth")


def send_confirmation(registration: PendingRegistration) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = registration.email
    message["Subject"] = "Confirm your FreeSelfTrack registration"
    # Fragment is not sent in HTTP requests/access logs or Referer headers.
    link = (
        settings.public_app_url.rstrip("/") + "/#verify=" + create_verification_token(registration)
    )
    message.set_content(
        "If you requested registration, open this link and enter the password you chose. "
        "Do not confirm a registration you did not request. Existing accounts are unchanged.\n\n"
        + link
        + "\n\nThis link expires at "
        + registration.expires_at.isoformat()
        + " UTC. "
        "If it expires, submit the registration form again."
    )
    send_message(message)


def send_message(message: EmailMessage) -> None:
    settings = get_settings()
    smtp: smtplib.SMTP
    if settings.smtp_security == "tls":
        smtp = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
            context=ssl.create_default_context(),
        )
    else:
        smtp = smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        )
    with smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


class RegistrationMailService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RegistrationRepository(session)

    async def process_one(self) -> bool:
        now = datetime.now(UTC)
        registration = await self.repository.next_mail(now)
        if registration is None:
            await self.repository.clean_expired(now)
            await self.session.commit()
            return False
        try:
            await run_in_threadpool(send_confirmation, registration)
        except (OSError, smtplib.SMTPException):
            # SMTP exceptions can contain recipients/server responses: never log them.
            registration.attempts += 1
            registration.next_attempt_at = now + timedelta(
                seconds=min(300, 5 * 2 ** min(registration.attempts, 6))
            )
            logger.warning("auth outcome=confirmation_delivery_retry")
        else:
            registration.sent_at = datetime.now(UTC)
            logger.info("auth outcome=confirmation_delivered")
        await self.session.commit()
        return True
