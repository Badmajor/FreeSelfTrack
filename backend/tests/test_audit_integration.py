"""Real migration/role tests against an isolated disposable PostgreSQL container."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import OrganizationMember, SecurityEvent, TaskHistory, User, UserProfile
from app.schemas.domain import OrganizationCreate, ProjectCreate, TaskCreate, TaskUpdate
from app.services.domain import DomainService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AUDIT_INTEGRATION") != "1", reason="Opt-in disposable PostgreSQL audit tests"
)


@pytest.fixture(scope="module")
def audit_database():
    name = "fst025-" + uuid4().hex[:12]

    def docker(*args):
        return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout

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
            "--health-cmd",
            "pg_isready -U postgres",
            "--health-interval",
            "1s",
            "--health-retries",
            "30",
            "postgres:16-alpine",
        )
        # pg_isready loop runs only within our new disposable container.
        docker(
            "exec", name, "sh", "-c", "until pg_isready -h 127.0.0.1 -U postgres; do sleep 1; done"
        )
        port = docker("port", name, "5432").strip().rsplit(":", 1)[1]
        url = f"postgresql+asyncpg://postgres:disposable-test@127.0.0.1:{port}/postgres"

        def migrate(action, revision):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", action, revision],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "TRACKER_DATABASE_URL": url},
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr

        migrate("upgrade", "0018_audit_integrity")
        migrate("downgrade", "0017_attachment_scan_index")
        migrate("upgrade", "head")
        yield url, migrate
    finally:
        docker("rm", "-f", "-v", name)


async def test_append_only_application_role_and_transaction_rollback(audit_database):
    url, migrate = audit_database
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE ROLE audit_runtime NOLOGIN NOSUPERUSER"))
            await connection.execute(text("GRANT USAGE ON SCHEMA public TO audit_runtime"))
            await connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE "
                    "ON ALL TABLES IN SCHEMA public TO audit_runtime"
                )
            )
        async with AsyncSession(engine, expire_on_commit=False) as session:
            user = User(
                email="audit@example.com",
                is_system_admin=True,
                password_hash="not-a-credential",
                profile=UserProfile(first_name="Audit", last_name="Tester"),
            )
            session.add(user)
            await session.commit()
            actor = user.id
            service = DomainService(session)
            org = await service.create_organization(actor, OrganizationCreate(name="Audit"))
            project = await service.create_project(
                actor, ProjectCreate(organization_id=org.id, name="Audit")
            )
            session.add(OrganizationMember(organization_id=org.id, user_id=actor))
            await session.commit()
            statuses = await service.repository.list_statuses(project.id)
            task = await service.create_task(
                actor, project.id, TaskCreate(title="Before", status_id=statuses[0].id)
            )
            await service.update_task(actor, task.id, TaskUpdate(title="After"))
            history_id = await session.scalar(
                select(TaskHistory.id).where(TaskHistory.task_id == task.id)
            )
            assert history_id is not None
        for statement in (
            "UPDATE task_history SET event_type = 'forged'",
            "DELETE FROM task_history",
            "TRUNCATE task_history",
            "UPDATE security_events SET actor_id = NULL",
            "DELETE FROM security_events",
            "TRUNCATE security_events",
            "DELETE FROM tasks",  # Cascading deletion cannot erase history either.
        ):
            with pytest.raises(DBAPIError) as error:
                async with engine.begin() as connection:
                    await connection.execute(text("SET LOCAL ROLE audit_runtime"))
                    await connection.execute(text(statement))
            assert error.value.orig.sqlstate == "42501"
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(text("SET LOCAL ROLE audit_runtime"))
            async with AsyncSession(bind=connection) as session:
                service = DomainService(session)
                await service.update_task(actor, task.id, TaskUpdate(title="Rolled back"))
                await service.create_project(
                    actor, ProjectCreate(organization_id=org.id, name="Rolled back project")
                )
                assert len(list(await session.scalars(select(SecurityEvent)))) == 1
                # Service commit joins this externally owned transaction.
                assert len(list(await session.scalars(select(TaskHistory)))) == 2
            await transaction.rollback()
        async with AsyncSession(engine) as session:
            assert len(list(await session.scalars(select(TaskHistory)))) == 1
            assert await session.scalar(text("SELECT title FROM tasks")) == "After"
            assert len(list(await session.scalars(select(SecurityEvent)))) == 1
        # A real committed write by the restricted runtime role must still succeed.
        async with engine.connect() as connection:
            await connection.execute(text("SET ROLE audit_runtime"))
            await connection.commit()
            async with AsyncSession(bind=connection) as session:
                await DomainService(session).update_task(
                    actor, task.id, TaskUpdate(title="Committed")
                )
            await connection.execute(text("RESET ROLE"))
            await connection.commit()
        async with AsyncSession(engine) as session:
            assert len(list(await session.scalars(select(TaskHistory)))) == 2
    finally:
        await engine.dispose()
