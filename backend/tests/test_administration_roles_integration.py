"""Disposable PostgreSQL migration and concurrent bootstrap; never uses the shared database."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from legacy_audit_helpers import seed_legacy_audit
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from test_administration_roles import settings

from app.models import AdministrativeAuditEvent, User
from app.services.bootstrap import bootstrap_administrator

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ROLES_INTEGRATION") != "1", reason="Opt-in disposable PostgreSQL role tests"
)


@pytest.fixture
def roles_database():
    name = "fst031-" + uuid4().hex[:12]

    def docker(*args):
        return subprocess.run(
            ["docker", *args], check=True, capture_output=True, text=True, timeout=60
        ).stdout

    started = False
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=disposable-test",
            "-p",
            "127.0.0.1::5432",
            "postgres:16-alpine",
        )
        started = True
        docker(
            "exec", name, "sh", "-c", "until pg_isready -h 127.0.0.1 -U postgres; do sleep 1; done"
        )
        port = docker("port", name, "5432").strip().rsplit(":", 1)[1]
        url = f"postgresql+asyncpg://postgres:disposable-test@127.0.0.1:{port}/postgres"

        def migrate(revision, *, action="upgrade", success=True):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", action, revision],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "TRACKER_DATABASE_URL": url},
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert (result.returncode == 0) == success, result.stderr
            return result

        migrate("0019_administrative_audit")
        yield url, migrate
    finally:
        if started:
            docker("rm", "-f", "-v", name)


async def test_legacy_backfill_and_concurrent_bootstrap(roles_database):
    url, migrate = roles_database
    engine = create_async_engine(url)
    active, inactive, ordinary = uuid4(), uuid4(), uuid4()
    org, archived_org = uuid4(), uuid4()
    project, archived_project = uuid4(), uuid4()
    async with engine.begin() as connection:
        await seed_legacy_audit(connection)
        for identifier, enabled in ((active, True), (inactive, False), (ordinary, True)):
            await connection.execute(
                text("""INSERT INTO users
                (id,email,password_hash,is_active,created_at,updated_at)
                VALUES (:id,:email,'preserved-hash',:active,now(),now())"""),
                {"id": identifier, "email": str(identifier), "active": enabled},
            )
        for identifier, owner, archived in ((org, active, False), (archived_org, inactive, True)):
            await connection.execute(
                text("""INSERT INTO organizations(id,owner_id,name,deleted_at)
                VALUES (:id,:owner,'Legacy',CASE WHEN :archived THEN now() ELSE NULL END)"""),
                {"id": identifier, "owner": owner, "archived": archived},
            )
        for identifier, parent, owner in (
            (project, org, inactive),
            (archived_project, archived_org, active),
        ):
            await connection.execute(
                text("""INSERT INTO projects(id,organization_id,owner_id,name)
                VALUES (:id,:parent,:owner,'Legacy')"""),
                {"id": identifier, "parent": parent, "owner": owner},
            )
        # Ordinary project member without organization membership must not gain access.
        await connection.execute(
            text("INSERT INTO project_members(project_id,user_id) VALUES (:p,:u)"),
            {"p": project, "u": ordinary},
        )
        await connection.execute(
            text("""INSERT INTO security_events
            (id,event_type,actor_kind,target_type,request_id,created_at,details)
            VALUES (:id,'legacy','anonymous','user',:request,now(),'{}')"""),
            {"id": uuid4(), "request": uuid4()},
        )
        before = list(
            await connection.scalars(
                text("SELECT row_to_json(t)::text FROM security_events t ORDER BY id")
            )
        )
    async with engine.connect() as connection:
        preserved = {}
        for table in ("tasks", "task_history", "project_statuses", "task_links"):
            preserved[table] = list(
                await connection.scalars(
                    text(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id")
                )
            )
    await engine.dispose()
    migrate("0020_administration_roles")
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                text(
                    "SELECT role FROM organization_members WHERE organization_id=:o AND user_id=:u"
                ),
                {"o": org, "u": active},
            )
            == "manager"
        )
        assert (
            await connection.scalar(
                text("SELECT state FROM project_members WHERE project_id=:p AND user_id=:u"),
                {"p": project, "u": inactive},
            )
            == "revoked"
        )
        assert (
            await connection.scalar(
                text("SELECT state FROM project_members WHERE project_id=:p AND user_id=:u"),
                {"p": project, "u": ordinary},
            )
            == "revoked"
        )
        assert (
            await connection.scalar(
                text("SELECT state FROM project_members WHERE project_id=:p AND user_id=:u"),
                {"p": archived_project, "u": active},
            )
            == "archived"
        )
    await engine.dispose()
    migrate("head")

    async def bootstrap():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await bootstrap_administrator(session, settings())

    try:
        await asyncio.gather(*(bootstrap() for _ in range(5)))
        async with AsyncSession(engine) as session:
            users = list(await session.scalars(select(User).where(User.is_system_admin.is_(True))))
            assert len(users) == 1 and users[0].email == "local administrator"
            events = list(await session.scalars(select(AdministrativeAuditEvent)))
            assert [event.action for event in events].count("user_created") == 1
            assert [event.action for event in events].count("system_role_changed") == 1
            for table, rows in preserved.items():
                assert (
                    list(
                        await session.scalars(
                            text(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id")
                        )
                    )
                    == rows
                )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname='fk_tasks_project_status_same_project'"
                    )
                )
                == 1
            )

            assert (
                list(
                    await session.scalars(
                        text("SELECT row_to_json(t)::text FROM security_events t ORDER BY id")
                    )
                )
                == before
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name IN ('organizations','projects') "
                        "AND column_name='owner_id'"
                    )
                )
                == 0
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM users WHERE password_hash='preserved-hash'")
                )
                == 3
            )
        await engine.dispose()
        failed = migrate("0020_administration_roles", action="downgrade", success=False)
        assert "Ownership cannot be reconstructed" in failed.stderr
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0021_remove_ownership"
            )
    finally:
        await engine.dispose()


async def test_clean_upgrade_bootstrap_and_login_race(roles_database):
    from app.schemas.domain import LoginRequest
    from app.services.auth import AuthService
    from app.services.errors import InvalidCredentialsError
    from app.services.sessions import SessionService

    url, migrate = roles_database
    migrate("head")
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await bootstrap_administrator(session, settings())

        async def login():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                return await AuthService(session).login(
                    LoginRequest(email="local administrator", password="x")
                )

        async def change():
            async with AsyncSession(engine, expire_on_commit=False) as session:
                await bootstrap_administrator(session, settings(password="changed"))

        result, changed = await asyncio.gather(login(), change(), return_exceptions=True)
        assert changed is None
        assert isinstance(result, (tuple, InvalidCredentialsError))
        if isinstance(result, tuple):
            async with AsyncSession(engine) as session:
                with pytest.raises(InvalidCredentialsError):
                    await SessionService(session).authenticate(result[0])
    finally:
        await engine.dispose()
