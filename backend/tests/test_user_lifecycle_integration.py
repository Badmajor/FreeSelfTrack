"""Disposable PostgreSQL verification for the user lifecycle and credential races."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_administration_roles_integration import roles_database  # noqa: F401

from app.models import User, UserProfile
from app.models.auth_session import PasswordReset
from app.models.registration import PendingRegistration
from app.schemas.domain import LoginRequest
from app.schemas.user_lifecycle import AdministrativeUserCreate
from app.services.auth import AuthService, password_hash
from app.services.errors import AdministrativeError, InvalidCredentialsError
from app.services.sessions import SessionService
from app.services.user_lifecycle import UserLifecycleService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_USER_LIFECYCLE_INTEGRATION") != "1",
    reason="Opt-in disposable PostgreSQL user lifecycle tests",
)
PASSWORD = "a permanent integration password"


async def test_migration_and_concurrent_user_lifecycle(roles_database):  # noqa: F811
    url, migrate = roles_database
    migrate("0021_remove_ownership")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            admin = User(
                email="admin@example.com",
                password_hash=password_hash.hash(PASSWORD),
                is_system_admin=True,
                profile=UserProfile(first_name="System", last_name="Admin"),
            )
            session.add(admin)
            await session.flush()
            now = datetime.now(UTC)
            session.add_all(
                [
                    PendingRegistration(
                        email="old@example.com",
                        password_hash=password_hash.hash(PASSWORD),
                        first_name="Pending",
                        last_name="User",
                        expires_at=now + timedelta(hours=1),
                        next_attempt_at=now,
                    ),
                    PasswordReset(
                        user_id=admin.id,
                        email=admin.email,
                        token_hash="f" * 64,
                        expires_at=now + timedelta(hours=1),
                        next_attempt_at=now,
                    ),
                ]
            )
            await session.commit()
            admin_id = admin.id
        migrate("head")
        async with factory() as session:
            assert await session.scalar(select(PendingRegistration)) is None
            assert await session.scalar(select(PasswordReset)) is None
            assert (
                await session.scalar(text("select version_num from alembic_version"))
                == "0022_disable_public_auth"
            )
        migrate("0021_remove_ownership", action="downgrade")
        migrate("head")

        async def create():
            async with factory() as session:
                return await UserLifecycleService(session).create(
                    admin_id,
                    AdministrativeUserCreate(
                        email="concurrent@example.com", first_name="Concurrent", last_name="User"
                    ),
                )

        results = await asyncio.gather(create(), create(), return_exceptions=True)
        successes = [result for result in results if not isinstance(result, BaseException)]
        assert len(successes) == 1
        assert (
            sum(
                isinstance(result, AdministrativeError) and result.code == "email_in_use"
                for result in results
            )
            == 1
        )
        target = successes[0].user.id
        temporary = successes[0].temporary_password
        async with factory() as session:
            access, _, _ = await AuthService(session).login(
                LoginRequest(email="concurrent@example.com", password=temporary)
            )

        async def change():
            async with factory() as session:
                await AuthService(session).change_password(target, temporary, PASSWORD)

        async def reset():
            async with factory() as session:
                return await UserLifecycleService(session).reset(admin_id, target)

        changed, reset_result = await asyncio.gather(change(), reset(), return_exceptions=True)
        assert changed is None or isinstance(changed, InvalidCredentialsError)
        assert not isinstance(reset_result, BaseException)
        async with factory() as session:
            with pytest.raises(InvalidCredentialsError):
                await SessionService(session).authenticate(access)
            user = await session.get(User, target)
            assert user.must_change_password
            assert password_hash.verify(reset_result.temporary_password, user.password_hash)

        async def login():
            async with factory() as session:
                return await AuthService(session).login(
                    LoginRequest(
                        email="concurrent@example.com", password=reset_result.temporary_password
                    )
                )

        async def block():
            async with factory() as session:
                return await UserLifecycleService(session).set_blocked(admin_id, target, True)

        logged_in, blocked = await asyncio.gather(login(), block(), return_exceptions=True)
        assert not isinstance(blocked, BaseException)
        assert isinstance(logged_in, (tuple, InvalidCredentialsError))
        async with factory() as session:
            if isinstance(logged_in, tuple):
                with pytest.raises(InvalidCredentialsError):
                    await SessionService(session).authenticate(logged_in[0])
            assert not (await session.get(User, target)).is_active
    finally:
        await engine.dispose()
