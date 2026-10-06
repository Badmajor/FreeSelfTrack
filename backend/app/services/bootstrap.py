from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.models import User, UserProfile
from app.repositories.administration import AdministrationRepository
from app.repositories.sessions import SessionRepository
from app.schemas.administrative_audit import AdministrativeAuditWrite, AuditChange
from app.services.administrative_audit import AdministrativeAuditService
from app.services.audit import record_event
from app.services.auth import password_hash


async def bootstrap_administrator(session: AsyncSession, settings: Settings) -> None:
    repository = AdministrationRepository(session)
    async with session.begin():
        await repository.lock_lifecycle()
        users = await repository.bootstrap_users(settings.admin_email)
        selected = next((user for user in users if user.email == settings.admin_email), None)
        audit = AdministrativeAuditService(session)
        if selected is None:
            selected = User(
                id=uuid4(),
                email=settings.admin_email,
                is_active=True,
                is_system_admin=False,
                must_change_password=False,
                password_hash="",
                profile=UserProfile(first_name="", last_name=""),
            )
            session.add(selected)
            users.append(selected)
            audit.record(
                AdministrativeAuditWrite(
                    actor_kind="bootstrap",
                    actor_id=None,
                    entity_type="user",
                    entity_id=selected.id,
                    action="user_created",
                    changes=(AuditChange(field="is_active", old=None, new=True),),
                )
            )
        for user in users:
            desired_role = user is selected
            changed = user.is_system_admin != desired_role
            audit.record(
                AdministrativeAuditWrite(
                    actor_kind="bootstrap",
                    actor_id=None,
                    entity_type="user",
                    entity_id=user.id,
                    action="system_role_changed",
                    changes=(
                        AuditChange(
                            field="is_system_admin", old=user.is_system_admin, new=desired_role
                        ),
                    ),
                )
            )
            user.is_system_admin = desired_role
            if desired_role:
                if user.profile is None:
                    user.profile = UserProfile(first_name="", last_name="")
                password = settings.admin_password.get_secret_value()
                same_password = bool(user.password_hash) and await run_in_threadpool(
                    password_hash.verify, password, user.password_hash
                )
                changed = (
                    changed or not same_password or not user.is_active or user.must_change_password
                )
                if not user.is_active:
                    audit.record(
                        AdministrativeAuditWrite(
                            actor_kind="bootstrap",
                            actor_id=None,
                            entity_type="user",
                            entity_id=user.id,
                            action="user_unblocked",
                            changes=(AuditChange(field="is_active", old=False, new=True),),
                        )
                    )
                user.is_active = True
                user.must_change_password = False
                if not same_password:
                    user.password_hash = await run_in_threadpool(password_hash.hash, password)
            if changed:
                for session_id in await SessionRepository(session).revoke_all(
                    user.id, datetime.now(UTC)
                ):
                    record_event(
                        session,
                        "session_revoked",
                        actor_id=None,
                        actor_kind="bootstrap",
                        target_type="session",
                        target_id=session_id,
                    )
                await repository.cancel_registration(user.email)
