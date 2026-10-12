"""Disposable PostgreSQL migration, email races and outbox locking."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_administration_roles import settings
from test_administration_roles_integration import roles_database  # noqa: F401

from app.models import User, UserProfile
from app.models.email_change import EmailChangeRequest
from app.repositories.email_change import EmailChangeRepository
from app.services.auth import password_hash
from app.services.bootstrap import bootstrap_administrator
from app.services.email_change import EmailChangeService, email_change_token
from app.services.email_change_mail import EmailChangeMailService
from app.services.errors import AdministrativeError

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_USER_CARDS_INTEGRATION") != "1",
    reason="Opt-in disposable PostgreSQL user cards/email tests",
)


async def test_migration_email_races_bootstrap_and_smtp_locking(roles_database, monkeypatch):  # noqa: F811
    url, migrate = roles_database
    migrate("0024_archive_lifecycle")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            users = [
                User(
                    id=uuid4(),
                    email=f"user{i}@example.com",
                    password_hash=password_hash.hash("fixture"),
                    is_system_admin=i == 0,
                    profile=UserProfile(first_name="Test", last_name=str(i)),
                )
                for i in range(4)
            ]
            session.add_all(users)
            await session.commit()
            admin, first, second, third = [user.id for user in users]
        migrate("head")
        async with factory() as session:
            await EmailChangeService(session).request(first, "pending@example.com")
        migrate("0024_archive_lifecycle", action="downgrade")
        migrate("head")
        async with factory() as session:
            assert await session.scalar(select(EmailChangeRequest)) is None
            assert await session.scalar(text("select count(*) from users")) == 4
            assert (
                await session.scalar(text("select version_num from alembic_version"))
                == "0025_email_change"
            )
            assert (
                await session.scalar(
                    text("""select confdeltype from pg_constraint
                where conrelid = 'email_change_requests'::regclass and contype = 'f'""")
                )
                == b"c"
            )

        async def request(identifier, email):
            async with factory() as session:
                await EmailChangeService(session).request(identifier, email)
                pending = await EmailChangeRepository(session).get(identifier)
                return email_change_token(pending.request_id)

        async def token(identifier):
            async with factory() as session:
                pending = await EmailChangeRepository(session).get(identifier)
                return email_change_token(pending.request_id)

        async def confirm(identifier, credential):
            async with factory() as session:
                await EmailChangeService(session).confirm(identifier, credential)

        # Two requests serialize: only the latest row survives, and confirmation is single-use.
        await asyncio.gather(
            request(first, "first@example.com"), request(first, "latest@example.com")
        )
        current = await token(first)
        results = await asyncio.gather(
            confirm(first, current), confirm(first, current), return_exceptions=True
        )
        assert results.count(None) == 1
        assert (
            sum(
                isinstance(r, AdministrativeError) and r.code == "invalid_email_token"
                for r in results
            )
            == 1
        )

        # Separate users can request the same unreserved address; only one can claim it.
        one, two = await asyncio.gather(
            request(first, "shared@example.com"), request(second, "shared@example.com")
        )
        results = await asyncio.gather(
            confirm(first, one), confirm(second, two), return_exceptions=True
        )
        assert results.count(None) == 1
        assert (
            sum(isinstance(r, AdministrativeError) and r.code == "email_in_use" for r in results)
            == 1
        )

        credential = await request(third, "self@example.com")

        async def direct():
            async with factory() as session:
                await EmailChangeService(session).change_direct(admin, third, "direct@example.com")

        results = await asyncio.gather(confirm(third, credential), direct(), return_exceptions=True)
        assert results[0] is None or isinstance(results[0], AdministrativeError)
        assert results[1] is None
        async with factory() as session:
            assert (await session.get(User, third)).email == "direct@example.com"
            assert await session.get(EmailChangeRequest, third) is None

        # Promotion through bootstrap cancels outstanding actions and protects the new admin.
        await request(third, "cancelled@example.com")
        async with factory() as session:
            await bootstrap_administrator(session, settings("direct@example.com", "config"))
        async with factory() as session:
            assert await session.get(EmailChangeRequest, third) is None
            with pytest.raises(AdministrativeError, match="deployment configuration"):
                await EmailChangeService(session).request(third, "forbidden@example.com")

        # Two workers cannot send the same pending row concurrently.
        async with factory() as session:
            await session.execute(delete(EmailChangeRequest))
            await session.commit()
        await request(first, "mail@example.com")
        sent = []
        monkeypatch.setattr(
            "app.services.email_change_mail.send_email_change",
            lambda pending: sent.append(pending.request_id),
        )

        async def worker():
            async with factory() as session:
                return await EmailChangeMailService(session).process_one()

        results = await asyncio.gather(worker(), worker())
        assert sorted(results) == [False, True]
        assert len(sent) == 1
    finally:
        await engine.dispose()
