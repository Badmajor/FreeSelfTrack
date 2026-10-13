# ruff: noqa: F811
"""Disposable PostgreSQL legacy migration, rollback and archive/write serialization."""

import asyncio
import os
from datetime import date
from uuid import uuid4

import pytest
from legacy_audit_helpers import seed_legacy_audit
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_administration_roles_integration import roles_database  # noqa: F401

from app.models import AdministrativeAuditEvent, Organization, Project, Task, User
from app.repositories.archive import ArchiveRepository
from app.schemas.chat import CommentCreate
from app.schemas.domain import ConfirmRequest, TaskCreate
from app.services.administrative_audit import AdministrativeAuditService
from app.services.chat import ChatService
from app.services.deadlines import DeadlineService
from app.services.domain import DomainService
from app.services.errors import AdministrativeError

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ARCHIVE_INTEGRATION") != "1", reason="Opt-in disposable PostgreSQL archive tests"
)


async def test_legacy_migration_preserves_data_and_normalizes_cascade(roles_database):  # noqa: F811
    url, migrate = roles_database
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            ids = await seed_legacy_audit(connection)
            await connection.execute(
                text(
                    "UPDATE organizations SET deleted_at = '2020-01-02T03:04:05Z' WHERE id = :org"
                ),
                ids,
            )
            before = (
                await connection.execute(
                    text(
                        "SELECT id, status_id, created_by, reporter_id, assignee_id, updated_at "
                        "FROM tasks ORDER BY id"
                    )
                )
            ).all()
            history = (await connection.execute(text("SELECT * FROM task_history"))).all()
        migrate("0023_resource_descriptions")
        migrate("head")
        async with engine.connect() as connection:
            after = (
                await connection.execute(
                    text(
                        "SELECT id, status_id, created_by, reporter_id, assignee_id, updated_at "
                        "FROM tasks ORDER BY id"
                    )
                )
            ).all()
            assert before == after
            assert history == (await connection.execute(text("SELECT * FROM task_history"))).all()
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM tasks WHERE archived_at = '2020-01-02T03:04:05Z'")
                )
                == 2
            )
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM projects WHERE archived_at = '2020-01-02T03:04:05Z'")
                )
                == 1
            )
            assert (
                await connection.scalar(text("SELECT count(*) FROM administrative_audit_events"))
                == 0
            )
            assert await connection.scalar(text("SELECT state FROM project_members")) == "archived"
        migrate("0023_resource_descriptions", action="downgrade", success=False)
    finally:
        await engine.dispose()


async def test_archive_serializes_writers_and_rolls_back_on_audit_failure(
    roles_database, monkeypatch
):  # noqa: F811
    url, migrate = roles_database
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            ids = await seed_legacy_audit(connection)
        migrate("head")
        async with factory() as session:
            user = await session.get(User, ids["user"])
            user.is_system_admin = True
            await session.commit()
        original_record = AdministrativeAuditService.record

        def reject_task(self, event):
            if event.entity_type == "task":
                raise RuntimeError("audit unavailable")
            return original_record(self, event)

        monkeypatch.setattr(AdministrativeAuditService, "record", reject_task)
        async with factory() as session:
            with pytest.raises(RuntimeError, match="audit unavailable"):
                await DomainService(session).archive_organization(
                    ids["user"], ids["org"], ConfirmRequest(confirm=True)
                )
            await session.rollback()
            assert (await session.get(Organization, ids["org"])).archived_at is None
            assert (await session.get(Project, ids["project"])).archived_at is None
            assert (
                await session.scalar(select(func.count()).select_from(AdministrativeAuditEvent))
                == 0
            )
        monkeypatch.setattr(AdministrativeAuditService, "record", original_record)
        entered, release = asyncio.Event(), asyncio.Event()
        original_tasks = ArchiveRepository.tasks

        async def pause(self, project_ids):
            result = await original_tasks(self, project_ids)
            entered.set()
            await release.wait()
            return result

        monkeypatch.setattr(ArchiveRepository, "tasks", pause)
        async with (
            factory() as archiver,
            factory() as creator,
            factory() as publisher,
            factory() as worker,
        ):
            # Stale ORM state and pre-upload authorization must not bypass the later lock.
            await ChatService(publisher).authorize(ids["user"], ids["task"])
            archive = asyncio.create_task(
                DomainService(archiver).archive_organization(
                    ids["user"], ids["org"], ConfirmRequest(confirm=True)
                )
            )
            await asyncio.wait_for(entered.wait(), 10)

            async def rejected(operation, transaction):
                try:
                    with pytest.raises(AdministrativeError):
                        await operation
                finally:
                    await transaction.rollback()

            creation = asyncio.create_task(
                rejected(
                    DomainService(creator).create_task(
                        ids["user"],
                        ids["project"],
                        TaskCreate(title="Race", status_id=ids["status"]),
                    ),
                    creator,
                )
            )
            publication = asyncio.create_task(
                rejected(
                    ChatService(publisher).create(
                        ids["user"], ids["task"], CommentCreate(text="Race", request_id=uuid4()), []
                    ),
                    publisher,
                )
            )
            notification = asyncio.create_task(
                DeadlineService(worker).process_due(date(2030, 1, 1))
            )
            await asyncio.sleep(0.1)
            assert not creation.done() and not publication.done() and not notification.done()
            release.set()
            await asyncio.wait_for(archive, 10)
            await asyncio.wait_for(asyncio.gather(creation, publication), 10)
            assert await asyncio.wait_for(notification, 10) == 0
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(Task)) == 2
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AdministrativeAuditEvent)
                    .where(AdministrativeAuditEvent.action == "archived")
                )
                == 4
            )
            assert (await session.get(Task, ids["task"])).archived_at is not None
    finally:
        await engine.dispose()


async def test_restore_serializes_new_membership_without_revoking_it(roles_database, monkeypatch):  # noqa: F811
    """A membership requested during restore is applied after the old grants are revoked."""
    from app.models import OrganizationMember, ProjectMember
    from app.services.memberships import MembershipService

    url, migrate = roles_database
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    entered, release = asyncio.Event(), asyncio.Event()
    try:
        async with engine.begin() as connection:
            ids = await seed_legacy_audit(connection)
        migrate("head")
        async with factory() as session:
            admin = await session.get(User, ids["user"])
            admin.is_system_admin = True
            await session.commit()
            await DomainService(session).archive_organization(
                ids["user"], ids["org"], ConfirmRequest(confirm=True)
            )
        original = ArchiveRepository.memberships

        async def pause(self, organization_id, project_ids, *, restore):
            await original(self, organization_id, project_ids, restore=restore)
            if restore:
                entered.set()
                await release.wait()

        monkeypatch.setattr(ArchiveRepository, "memberships", pause)
        async with factory() as restorer, factory() as adder:
            restoration = asyncio.create_task(
                DomainService(restorer).restore_organization(ids["user"], ids["org"])
            )
            try:
                await asyncio.wait_for(entered.wait(), 10)
                addition = asyncio.create_task(
                    MembershipService(adder).put(
                        ids["user"], "organization", ids["org"], ids["user"], "manager"
                    )
                )
                await asyncio.sleep(0.1)
                assert not addition.done()
            finally:
                release.set()
            await asyncio.wait_for(asyncio.gather(restoration, addition), 10)
        async with factory() as session:
            membership = await session.get(OrganizationMember, (ids["org"], ids["user"]))
            assert (membership.role, membership.state) == ("manager", "active")
            project_membership = await session.get(ProjectMember, (ids["project"], ids["user"]))
            assert project_membership.state == "revoked"
            # An idempotent second restore must not erase the new membership.
            await DomainService(session).restore_organization(ids["user"], ids["org"])
            await session.refresh(membership)
            assert membership.state == "active" and membership.role == "manager"
    finally:
        release.set()
        await engine.dispose()
