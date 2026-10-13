"""Descriptions and concurrent role upserts on a disposable PostgreSQL database."""

import asyncio
import os

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_administration_roles_integration import roles_database  # noqa: F401

from app.models import Organization, OrganizationMember, Project, ProjectMember, User, UserProfile
from app.models.administrative_audit import AdministrativeAuditEvent
from app.schemas.domain import OrganizationCreate, ProjectCreate
from app.services.domain import DomainService
from app.services.memberships import MembershipService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MEMBERSHIP_INTEGRATION") != "1",
    reason="Opt-in disposable PostgreSQL membership tests",
)


async def test_description_migration_and_concurrent_membership(roles_database):  # noqa: F811
    url, migrate = roles_database
    migrate("0022_disable_public_auth")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO organizations(id,name) VALUES (gen_random_uuid(),'Legacy')")
            )
        # Verify 0023's round trip before the irreversible 0024 archive contract.
        migrate("0023_resource_descriptions")
        async with factory() as session:
            assert await session.scalar(text("SELECT description FROM organizations")) is None
        migrate("0022_disable_public_auth", action="downgrade")
        migrate("head")
        async with factory() as session:
            admin = User(
                email="admin",
                password_hash="unused",
                is_system_admin=True,
                profile=UserProfile(first_name="System", last_name="Admin"),
            )
            target = User(
                email="target",
                password_hash="unused",
                profile=UserProfile(first_name="Target", last_name="User"),
            )
            session.add_all([admin, target])
            await session.commit()
            admin_id, target_id = admin.id, target.id
            org = await DomainService(session).create_organization(
                admin_id, OrganizationCreate(name="Concurrent", description="Org description")
            )
            project = await DomainService(session).create_project(
                admin_id,
                ProjectCreate(
                    organization_id=org.id, name="Concurrent", description="Project description"
                ),
            )
            org_id, project_id = org.id, project.id

        async def add(scope, identifier):
            async with factory() as session:
                return await MembershipService(session).put(
                    admin_id, scope, identifier, target_id, "manager"
                )

        for scope, identifier, model in (
            ("organization", org_id, OrganizationMember),
            ("project", project_id, ProjectMember),
        ):
            results = await asyncio.gather(*(add(scope, identifier) for _ in range(5)))
            assert all(result.role == "manager" for result in results)
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(model)) == 1
                events = list(
                    await session.scalars(
                        select(AdministrativeAuditEvent).where(
                            AdministrativeAuditEvent.action == "member_added",
                            AdministrativeAuditEvent.entity_type == scope,
                        )
                    )
                )
                assert len(events) == 1
                user_events = list(
                    await session.scalars(
                        select(AdministrativeAuditEvent).where(
                            AdministrativeAuditEvent.entity_type == "user",
                            AdministrativeAuditEvent.operation_id == events[0].operation_id,
                        )
                    )
                )
                assert len(user_events) == 1
        async with factory() as session:
            assert (await session.get(Organization, org_id)).description == "Org description"
            assert (await session.get(Project, project_id)).description == "Project description"
    finally:
        await engine.dispose()
