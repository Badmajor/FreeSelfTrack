"""PostgreSQL query parity and membership revocation versus comment publication."""

import asyncio
import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_administration_roles_integration import roles_database  # noqa: F401

from app.models import Comment, Notification, OrganizationMember, ProjectMember, User, UserProfile
from app.repositories.administration import AdministrationRepository
from app.repositories.domain import DomainRepository
from app.schemas.chat import CommentCreate
from app.schemas.domain import OrganizationCreate, ProjectCreate, TaskCreate, TaskLinkCreate
from app.services.chat import ChatService
from app.services.domain import DomainService
from app.services.errors import AdministrativeError

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TASK_ACCESS_INTEGRATION") != "1",
    reason="Opt-in disposable PostgreSQL task access tests",
)


async def test_revocation_serializes_comment_and_filters_link_payloads(roles_database):  # noqa: F811
    url, migrate = roles_database
    migrate("head")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            admin = User(
                email="access-admin",
                password_hash="unused",
                is_system_admin=True,
                profile=UserProfile(first_name="Admin", last_name="Test"),
            )
            member = User(
                email="access-member",
                password_hash="unused",
                profile=UserProfile(first_name="Member", last_name="Test"),
            )
            session.add_all([admin, member])
            await session.commit()
            actor, target = admin.id, member.id
            domain = DomainService(session)
            org = await domain.create_organization(actor, OrganizationCreate(name="Access"))
            projects = [
                await domain.create_project(actor, ProjectCreate(organization_id=org.id, name=name))
                for name in ("First", "Second")
            ]
            session.add(OrganizationMember(organization_id=org.id, user_id=target))
            for project in projects:
                session.add(ProjectMember(project_id=project.id, user_id=target))
            await session.commit()
            tasks = []
            for project in projects:
                statuses = await domain.repository.list_statuses(project.id)
                tasks.append(
                    await domain.create_task(
                        actor,
                        project.id,
                        TaskCreate(title="Secret", status_id=statuses[0].id, reporter_id=target),
                    )
                )
            link, _ = await domain.create_task_link(
                actor,
                tasks[0].id,
                TaskLinkCreate(target_task_id=tasks[1].id, relation_type="related"),
            )
            notification = (await domain.list_notifications(target))[0]
            assert len((await domain.get_task_history(target, tasks[0].id, 50, None)).entries) == 1
            assert await domain.unread_notification_count(target)
            assert await domain.repository.list_due_tasks(date(2030, 1, 1), 50) == []
            ids = [task.id for task in tasks]
            project_ids = [project.id for project in projects]

        async with factory() as writer, factory() as remover:
            chat = ChatService(writer)
            # Simulate authorization/candidate selection before parsing a long upload.
            await chat.authorize(actor, ids[0])
            await AdministrationRepository(remover).lock_lifecycle()
            membership = await remover.get(
                ProjectMember, {"project_id": project_ids[0], "user_id": target}
            )
            membership.state = "revoked"
            await remover.flush()
            publication = asyncio.create_task(
                chat.create(
                    actor,
                    ids[0],
                    CommentCreate(text="Stale mention", mention_ids=[target], request_id=uuid4()),
                    [],
                )
            )
            await asyncio.sleep(0.1)
            assert not publication.done()
            await remover.commit()
            with pytest.raises(AdministrativeError, match="cannot view"):
                await asyncio.wait_for(publication, timeout=10)
            await writer.rollback()

        async with factory() as session:
            domain = DomainService(session)
            assert await session.scalar(select(func.count()).select_from(Comment)) == 0
            assert await session.scalar(select(func.count()).select_from(Notification)) == 1
            assert await domain.list_notifications(target) == []
            assert (await domain.unread_notification_count(target)).count == 0
            assert await DomainRepository(session).get_notification(notification.id, target) is None
            # The second task remains readable, but neither link nor history reveals the first.
            assert await domain.list_task_links(target, ids[1]) == []
            assert (await domain.get_task_history(target, ids[1], 50, None)).entries == []
            assert link.task.id == ids[1]
    finally:
        await engine.dispose()
