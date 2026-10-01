import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

import jwt

from app.core.config import get_settings
from app.models.registration import PendingRegistration
from app.services.errors import DomainError


class InvalidVerificationError(DomainError):
    status_code = 400


def verification_key() -> bytes:
    return hmac.new(
        get_settings().auth_secret_key.encode(), b"email-verification-v1", hashlib.sha256
    ).digest()


def create_verification_token(registration: PendingRegistration) -> str:
    return jwt.encode(
        {"sub": str(registration.id), "exp": registration.expires_at, "aud": "email-verification"},
        verification_key(),
        algorithm="HS256",
    )


def read_verification_token(token: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            verification_key(),
            algorithms=["HS256"],
            audience="email-verification",
            options={"require": ["sub", "exp", "aud"]},
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise InvalidVerificationError("Invalid or expired confirmation") from exc


def is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)
