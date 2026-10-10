import base64
import binascii
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models import OrganizationMember, User, UserProfile
from app.repositories.administration import AdministrationRepository
from app.repositories.domain import DomainRepository
from app.repositories.sessions import SessionRepository
from app.schemas.administrative_audit import AdministrativeAuditWrite, AuditChange
from app.schemas.domain import UserResponse
from app.schemas.user_lifecycle import (
    AdministrativeUserCreate,
    TemporaryPasswordResponse,
    UserCard,
    UserPage,
)
from app.services.administrative_audit import AdministrativeAuditService
from app.services.audit import record_event
from app.services.auth import password_hash
from app.services.auth_protection import normalize_email
from app.services.errors import AdministrativeError
from app.services.sessions import SessionService, invalid_session


class UserLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.administration = AdministrationRepository(session)
        self.domain = DomainRepository(session)
        self.sessions = SessionRepository(session)
        self.audit = AdministrativeAuditService(session)

    async def _actor(self, actor_id: UUID, target_id: UUID | None = None) -> User:
        await self.administration.lock_lifecycle()
        actor = None
        for identifier in sorted({actor_id, target_id} if target_id else {actor_id}):
            locked = await self.sessions.lock_user(identifier)
            if identifier == actor_id:
                actor = locked
        await SessionService(self.session).recheck_request_session(actor_id)
        if actor is None or not actor.is_active:
            raise invalid_session()
        if actor.must_change_password:
            raise AdministrativeError(403, "password_change_required", "Password change required")
        return actor

    async def create(
        self, actor_id: UUID, data: AdministrativeUserCreate, organization_id: UUID | None = None
    ) -> TemporaryPasswordResponse:
        actor = await self._actor(actor_id)
        if organization_id is None:
            allowed = actor.is_system_admin
        else:
            allowed = actor.is_system_admin or await self.administration.active_manager(
                actor_id, organization_id
            )
        if not allowed:
            raise AdministrativeError(
                403, "permission_denied", "Administrative permission required"
            )
        if organization_id is not None:
            organization = await self.domain.get_organization(organization_id)
            if organization is None:
                raise AdministrativeError(404, "not_found", "Organization not found")
            if organization.deleted_at is not None:
                raise AdministrativeError(409, "object_archived", "Organization is archived")
        email = normalize_email(str(data.email))
        if await self.domain.get_user_by_email(email) is not None:
            raise AdministrativeError(409, "email_in_use", "Email is already in use")
        temporary = secrets.token_urlsafe(24)
        user = User(
            email=email,
            password_hash=await run_in_threadpool(password_hash.hash, temporary),
            must_change_password=True,
            profile=UserProfile(first_name=data.first_name, last_name=data.last_name),
        )
        self.session.add(user)
        await self.session.flush()
        changes = [
            AuditChange(field="first_name", old=None, new=data.first_name),
            AuditChange(field="last_name", old=None, new=data.last_name),
            AuditChange(field="is_active", old=None, new=True),
        ]
        if organization_id is not None:
            self.session.add(
                OrganizationMember(
                    organization_id=organization_id, user_id=user.id, role="member", state="active"
                )
            )
            membership = (
                AuditChange(field="organization_id", old=None, new=organization_id),
                AuditChange(field="role", old=None, new="member"),
                AuditChange(field="state", old=None, new="active"),
            )
            changes.extend(membership)
            self.audit.record(
                AdministrativeAuditWrite(
                    actor_id=actor_id,
                    entity_type="organization",
                    entity_id=organization_id,
                    action="member_added",
                    subject_user_id=user.id,
                    changes=membership,
                )
            )
        self.audit.record(
            AdministrativeAuditWrite(
                actor_id=actor_id,
                entity_type="user",
                entity_id=user.id,
                action="user_created",
                changes=tuple(changes),
            )
        )
        await self.session.commit()
        return TemporaryPasswordResponse(
            user=UserResponse.model_validate(user), temporary_password=temporary
        )

    async def _revoke(self, actor_id: UUID, target_id: UUID) -> None:
        for identifier in await self.sessions.revoke_all(target_id, datetime.now(UTC)):
            record_event(
                self.session,
                "session_revoked",
                actor_id=actor_id,
                target_type="session",
                target_id=identifier,
            )

    async def reset(self, actor_id: UUID, target_id: UUID) -> TemporaryPasswordResponse:
        actor = await self._actor(actor_id, target_id)
        if not actor.is_system_admin:
            raise AdministrativeError(403, "permission_denied", "System administrator required")
        user = await self.sessions.lock_user(target_id)
        if user is None:
            raise AdministrativeError(404, "not_found", "User not found")
        if user.is_system_admin:
            raise AdministrativeError(
                403, "system_admin_protected", "Configuration administrator is protected"
            )
        temporary = secrets.token_urlsafe(24)
        user.password_hash = await run_in_threadpool(password_hash.hash, temporary)
        user.must_change_password = True
        await self._revoke(actor_id, target_id)
        await self.session.commit()
        return TemporaryPasswordResponse(
            user=UserResponse.model_validate(user), temporary_password=temporary
        )

    async def set_blocked(self, actor_id: UUID, target_id: UUID, blocked: bool) -> User:
        actor = await self._actor(actor_id, target_id)
        if not actor.is_system_admin and not await self.administration.active_manager(actor_id):
            raise AdministrativeError(
                403, "permission_denied", "Administrative permission required"
            )
        user = await self.sessions.lock_user(target_id)
        if user is None:
            raise AdministrativeError(404, "not_found", "User not found")
        if blocked and user.is_system_admin:
            raise AdministrativeError(
                403, "system_admin_protected", "Configuration administrator is protected"
            )
        if user.is_active != (not blocked):
            user.is_active = not blocked
            if blocked:
                await self._revoke(actor_id, target_id)
                await self.administration.revoke_memberships(target_id)
            self.audit.record(
                AdministrativeAuditWrite(
                    actor_id=actor_id,
                    entity_type="user",
                    entity_id=target_id,
                    action="user_blocked" if blocked else "user_unblocked",
                    changes=(AuditChange(field="is_active", old=blocked, new=not blocked),),
                )
            )
        await self.session.commit()
        return user

    async def list_users(
        self, actor_id: UUID, query: str, state: str, cursor: str | None, limit: int
    ) -> UserPage:
        after = None
        if cursor:
            try:
                payload = json.loads(base64.urlsafe_b64decode(cursor))
                if (
                    not isinstance(payload, list)
                    or len(payload) != 4
                    or payload[:3] != ["users", query, state]
                ):
                    raise ValueError
                after = UUID(payload[3])
            except (ValueError, TypeError, AttributeError, binascii.Error) as exc:
                raise AdministrativeError(422, "invalid_cursor", "Invalid cursor") from exc
        actor = await self.domain.get_user(actor_id)
        if actor is None or not actor.is_active:
            raise invalid_session()
        can_block = actor.is_system_admin or await self.administration.active_manager(actor_id)
        users = await self.administration.users_page(query, state, after, limit)
        items = [
            UserCard(
                id=user.id,
                first_name=user.profile.first_name,
                last_name=user.profile.last_name,
                is_active=user.is_active,
                created_at=user.created_at,
                capabilities={
                    "block": can_block and user.is_active and not user.is_system_admin,
                    "unblock": can_block and not user.is_active,
                    "reset_password": actor.is_system_admin and not user.is_system_admin,
                    "edit_profile": False,
                    "change_email": False,
                    "view_audit": False,
                },
            )
            for user in users[:limit]
        ]
        next_cursor = None
        if len(users) > limit:
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(["users", query, state, str(items[-1].id)]).encode()
            ).decode()
        return UserPage(items=items, next_cursor=next_cursor)
