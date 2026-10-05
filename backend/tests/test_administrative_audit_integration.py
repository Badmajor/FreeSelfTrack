"""TASK-030 checks use a new disposable PostgreSQL container, never the shared stack."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import AdministrativeAuditEvent, User, UserProfile
from app.schemas.administrative_audit import AdministrativeAuditWrite, AuditChange
from app.schemas.domain import OrganizationCreate, ProjectCreate, TaskCreate, TaskUpdate
from app.services.administrative_audit import AdministrativeAuditService
from app.services.domain import DomainService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ADMINISTRATIVE_AUDIT_INTEGRATION") != "1",
    reason="Opt-in disposable PostgreSQL administrative audit tests",
)


@pytest.fixture(scope="module")
def administrative_audit_database():
    name = "fst030-" + uuid4().hex[:12]

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
        docker("exec", name, "sh", "-c", "until pg_isready -U postgres; do sleep 1; done")
        port = docker("port", name, "5432").strip().rsplit(":", 1)[1]
        url = f"postgresql+asyncpg://postgres:disposable-test@127.0.0.1:{port}/postgres"

        def migrate(action, revision, *, success=True):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", action, revision],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "TRACKER_DATABASE_URL": url},
                capture_output=True,
                text=True,
                timeout=60,
            )
            if success:
                assert result.returncode == 0, result.stderr
            else:
                assert result.returncode != 0
            return result

        migrate("upgrade", "0018_audit_integrity")
        yield url, migrate
    finally:
        if started:
            docker("rm", "-f", "-v", name)


async def test_migration_preserves_logs_and_runtime_atomicity(administrative_audit_database):
    url, migrate = administrative_audit_database
    engine = create_async_engine(url)

    async def legacy_snapshot():
        async with engine.connect() as connection:
            result = {}
            for table in ("task_history", "security_events"):
                rows = await connection.scalars(
                    text(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id")
                )
                result[table] = list(rows)
            return result

    def blocked_event(actor):
        return AdministrativeAuditWrite(
            actor_id=actor,
            entity_type="user",
            entity_id=actor,
            action="user_blocked",
            changes=(AuditChange(field="is_active", old=True, new=False),),
        )

    try:
        # Seed genuine existing task history/security records BEFORE migration 0019.
        async with AsyncSession(engine, expire_on_commit=False) as session:
            user = User(
                email="legacy-audit@example.com",
                password_hash="not-a-credential",
                profile=UserProfile(first_name="Legacy", last_name="Audit"),
            )
            session.add(user)
            await session.commit()
            actor = user.id
            service = DomainService(session)
            org = await service.create_organization(actor, OrganizationCreate(name="Legacy"))
            project = await service.create_project(
                actor, ProjectCreate(organization_id=org.id, name="Legacy")
            )
            statuses = await service.repository.list_statuses(project.id)
            task = await service.create_task(
                actor, project.id, TaskCreate(title="Before", status_id=statuses[0].id)
            )
            await service.update_task(actor, task.id, TaskUpdate(title="After"))
        before = await legacy_snapshot()
        assert all(before.values())
        await engine.dispose()
        migrate("upgrade", "head")
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT count(*) FROM administrative_audit_events"))
                == 0
            )
        assert await legacy_snapshot() == before
        await engine.dispose()
        migrate("downgrade", "0018_audit_integrity")
        assert await legacy_snapshot() == before
        await engine.dispose()
        migrate("upgrade", "head")
        assert await legacy_snapshot() == before
        async with engine.begin() as connection:
            await connection.execute(text("CREATE ROLE admin_audit_runtime NOLOGIN NOSUPERUSER"))
            await connection.execute(text("GRANT USAGE ON SCHEMA public TO admin_audit_runtime"))
            await connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE "
                    "ON ALL TABLES IN SCHEMA public TO admin_audit_runtime"
                )
            )
            triggers = (
                await connection.execute(
                    text(
                        "SELECT tgname, tgenabled::text FROM pg_trigger "
                        "WHERE tgrelid = 'administrative_audit_events'::regclass "
                        "AND NOT tgisinternal"
                    )
                )
            ).all()
            assert sorted(triggers) == [
                ("administrative_audit_immutable", "A"),
                ("administrative_audit_no_truncate", "A"),
            ]

        # Restricted-role INSERT and its domain change roll back together.
        async with AsyncSession(engine) as session:
            await session.execute(text("SET LOCAL ROLE admin_audit_runtime"))
            await session.execute(update(User).where(User.id == actor).values(is_active=False))
            AdministrativeAuditService(session).record(blocked_event(actor))
            await session.flush()
            await session.rollback()
        async with engine.connect() as connection:
            assert await connection.scalar(select(User.is_active).where(User.id == actor)) is True
            assert (
                await connection.scalar(text("SELECT count(*) FROM administrative_audit_events"))
                == 0
            )

        # A failed audit INSERT must also prevent committing the domain mutation.
        async with AsyncSession(engine) as session:
            await session.execute(text("SET LOCAL ROLE admin_audit_runtime"))
            await session.execute(update(User).where(User.id == actor).values(is_active=False))
            event = AdministrativeAuditService(session).record(blocked_event(actor))
            event.actor_id = None
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
        async with engine.connect() as connection:
            assert await connection.scalar(select(User.is_active).where(User.id == actor)) is True
            assert (
                await connection.scalar(text("SELECT count(*) FROM administrative_audit_events"))
                == 0
            )

        # A successful restricted-role transaction persists both records.
        async with AsyncSession(engine) as session:
            await session.execute(text("SET LOCAL ROLE admin_audit_runtime"))
            await session.execute(update(User).where(User.id == actor).values(is_active=False))
            AdministrativeAuditService(session).record(blocked_event(actor))
            await session.commit()
        async with engine.connect() as connection:
            assert await connection.scalar(select(User.is_active).where(User.id == actor)) is False
            assert (
                await connection.scalar(text("SELECT count(*) FROM administrative_audit_events"))
                == 1
            )
            # Model/migration columns and index agree for the new table.
            columns = set(
                await connection.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'administrative_audit_events'"
                    )
                )
            )
            assert columns == set(AdministrativeAuditEvent.__table__.columns.keys())
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_indexes "
                        "WHERE indexname = 'ix_administrative_audit_entity_time'"
                    )
                )
                == 1
            )

        for table in ("administrative_audit_events", "task_history", "security_events"):
            for statement in (
                f"UPDATE {table} SET id = id",
                f"DELETE FROM {table}",
                f"TRUNCATE {table}",
            ):
                with pytest.raises(DBAPIError) as error:
                    async with engine.begin() as connection:
                        await connection.execute(text("SET LOCAL ROLE admin_audit_runtime"))
                        await connection.execute(text(statement))
                assert error.value.orig.sqlstate == "42501"
        assert await legacy_snapshot() == before
        # Nonempty downgrade fails atomically and keeps the head/table/triggers intact.
        await engine.dispose()
        failed = migrate("downgrade", "0018_audit_integrity", success=False)
        assert "Cannot downgrade a nonempty administrative audit" in failed.stderr
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0019_administrative_audit"
            )
            assert (
                await connection.scalar(text("SELECT count(*) FROM administrative_audit_events"))
                == 1
            )
        assert await legacy_snapshot() == before
    finally:
        await engine.dispose()
