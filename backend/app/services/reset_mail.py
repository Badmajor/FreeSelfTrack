import logging
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

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
        """Legacy outbox is disabled; no registration/reset messages are sent."""
        return False
