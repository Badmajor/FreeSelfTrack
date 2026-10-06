import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import User
from app.models.auth_session import AuthSession, RefreshCredential
from app.repositories.administration import AdministrationRepository
from app.repositories.domain import DomainRepository
from app.repositories.sessions import SessionRepository
from app.services.audit import record_event
from app.services.errors import InvalidCredentialsError
from app.services.verification import is_expired


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def reset_token(reset_id: UUID) -> str:
    # Reconstructable by the durable SMTP worker, without persisting a raw credential.
    signature = hmac.new(
        get_settings().auth_secret_key.encode(),
        b"password-reset-v1:" + reset_id.bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"{reset_id}.{signature}"


def invalid_session() -> InvalidCredentialsError:
    return InvalidCredentialsError("Authentication required")


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid4()),
            "iss": settings.auth_issuer,
            "aud": settings.auth_audience,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )


def read_access_token(token: str) -> tuple[UUID, UUID]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=["HS256"],
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
            options={
                "require": ["sub", "sid", "jti", "iss", "aud", "type", "iat", "exp"],
                "strict_aud": True,
            },
        )
        if (
            payload["type"] != "access"
            or type(payload["iat"]) is not int
            or type(payload["exp"]) is not int
            or payload["exp"] <= payload["iat"]
            or payload["exp"] - payload["iat"] > settings.access_token_expire_minutes * 60
        ):
            raise ValueError("Invalid claims")
        UUID(payload["jti"])
        return UUID(payload["sub"]), UUID(payload["sid"])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError) as exc:
        raise invalid_session() from exc


class SessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = SessionRepository(session)

    async def start(self, user: User) -> tuple[str, str]:
        # Caller holds the user lock until this transaction commits.
        now = datetime.now(UTC)
        family = AuthSession(
            id=uuid4(),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(days=get_settings().refresh_expire_days),
        )
        self.session.add(family)
        await self.session.flush()
        refresh = self._issue_refresh(family.id)
        record_event(
            self.session,
            "login_succeeded",
            actor_id=user.id,
            target_type="session",
            target_id=family.id,
        )
        await self.session.commit()
        return create_access_token(user.id, family.id), refresh

    def _issue_refresh(self, session_id: UUID) -> str:
        token = secrets.token_urlsafe(48)
        self.session.add(RefreshCredential(token_hash=token_digest(token), session_id=session_id))
        return token

    async def authenticate(self, token: str) -> tuple[User, AuthSession]:
        user_id, session_id = read_access_token(token)
        user = await DomainRepository(self.session).get_user(user_id)
        family = await self.repository.get_session(session_id)
        if (
            user is None
            or not user.is_active
            or family is None
            or family.user_id != user_id
            or family.revoked_at is not None
            or is_expired(family.expires_at)
        ):
            raise invalid_session()
        return user, family

    async def recheck_request_session(self, user_id: UUID) -> None:
        """After a lifecycle lock, reject a request authenticated before revocation.

        Internal service callers have no HTTP session; they still validate the actor.
        The ID is set by authentication, never taken from domain request input.
        """
        session_id = self.session.info.get("authenticated_session_id")
        if session_id is None:
            return
        family = await self.repository.get_session(session_id)
        if (
            family is None
            or family.user_id != user_id
            or family.revoked_at is not None
            or is_expired(family.expires_at)
        ):
            raise invalid_session()

    async def refresh(self, token: str) -> tuple[str, str, User]:
        await AdministrationRepository(self.session).lock_lifecycle(shared=True)
        credential = await self.repository.get_refresh(token_digest(token))
        if credential is None:
            raise invalid_session()
        family = await self.repository.get_session(credential.session_id)
        if family is None:
            raise invalid_session()
        user = await self.repository.lock_user(family.user_id)
        family = await self.repository.get_session(family.id)
        credential = await self.repository.get_refresh(token_digest(token))
        if (
            user is None
            or not user.is_active
            or family is None
            or credential is None
            or family.revoked_at is not None
            or is_expired(family.expires_at)
        ):
            raise invalid_session()
        if credential.used_at is not None:
            family.revoked_at = datetime.now(UTC)
            record_event(
                self.session,
                "session_revoked_replay",
                actor_id=None,
                actor_kind="anonymous",
                target_type="session",
                target_id=family.id,
            )
            await self.session.commit()  # Revocation must survive the following 401.
            raise invalid_session()
        credential.used_at = datetime.now(UTC)
        refresh = self._issue_refresh(family.id)
        await self.session.commit()
        return create_access_token(user.id, family.id), refresh, user

    async def revoke_current(self, user_id: UUID, session_id: UUID) -> None:
        await self.repository.lock_user(user_id)
        family = await self.repository.get_session(session_id)
        if family is None or family.user_id != user_id:
            raise invalid_session()
        if family.revoked_at is None:
            family.revoked_at = datetime.now(UTC)
            record_event(
                self.session,
                "session_revoked",
                actor_id=user_id,
                target_type="session",
                target_id=family.id,
            )
        await self.session.commit()

    async def logout(self, token: str) -> None:
        credential = await self.repository.get_refresh(token_digest(token))
        family = await self.repository.get_session(credential.session_id) if credential else None
        if family is None:
            raise invalid_session()
        await self.revoke_current(family.user_id, family.id)
