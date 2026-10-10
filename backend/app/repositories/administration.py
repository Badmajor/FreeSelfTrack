from uuid import UUID

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Organization, OrganizationMember, Project, ProjectMember, User, UserProfile
from app.models.registration import PendingRegistration

# Shared by bootstrap and lifecycle writers. Never upgrade a shared lock to exclusive.
ADMINISTRATION_LIFECYCLE_LOCK = 240031


class AdministrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_lifecycle(self, *, shared: bool = False) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
            await self.session.execute(
                text(f"SELECT {function}(:key)"), {"key": ADMINISTRATION_LIFECYCLE_LOCK}
            )

    async def bootstrap_users(self, email: str) -> list[User]:
        return list(
            await self.session.scalars(
                select(User)
                .where((User.email == email) | User.is_system_admin.is_(True))
                .options(selectinload(User.profile))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def cancel_registration(self, email: str) -> None:
        await self.session.execute(
            delete(PendingRegistration).where(PendingRegistration.email == email)
        )

    async def active_manager(
        self, user_id: UUID, organization_id: UUID | None = None, project_id: UUID | None = None
    ) -> bool:
        if project_id is not None:
            query = (
                select(ProjectMember.user_id)
                .join(Project, Project.id == ProjectMember.project_id)
                .join(Organization, Organization.id == Project.organization_id)
                .join(
                    OrganizationMember,
                    (OrganizationMember.organization_id == Organization.id)
                    & (OrganizationMember.user_id == ProjectMember.user_id),
                )
                .where(
                    ProjectMember.user_id == user_id,
                    ProjectMember.role == "manager",
                    ProjectMember.state == "active",
                    OrganizationMember.state == "active",
                    Project.deleted_at.is_(None),
                    Organization.deleted_at.is_(None),
                )
            )
            query = query.where(Project.id == project_id)
        else:
            query = (
                select(OrganizationMember.user_id)
                .join(Organization, Organization.id == OrganizationMember.organization_id)
                .where(
                    OrganizationMember.user_id == user_id,
                    OrganizationMember.role == "manager",
                    OrganizationMember.state == "active",
                    Organization.deleted_at.is_(None),
                )
            )
            if organization_id is not None:
                query = query.where(Organization.id == organization_id)
        return await self.session.scalar(query.limit(1)) is not None

    async def has_project_manager_role(self, user_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(ProjectMember.user_id)
                .join(Project, Project.id == ProjectMember.project_id)
                .join(Organization, Organization.id == Project.organization_id)
                .join(
                    OrganizationMember,
                    (OrganizationMember.organization_id == Organization.id)
                    & (OrganizationMember.user_id == ProjectMember.user_id),
                )
                .where(
                    ProjectMember.user_id == user_id,
                    ProjectMember.state == "active",
                    ProjectMember.role == "manager",
                    OrganizationMember.state == "active",
                    Organization.deleted_at.is_(None),
                    Project.deleted_at.is_(None),
                )
                .limit(1)
            )
            is not None
        )

    async def active_memberships(self, user_id: UUID) -> tuple[dict[UUID, str], dict[UUID, str]]:
        organizations = await self.session.execute(
            select(OrganizationMember.organization_id, OrganizationMember.role)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.state == "active",
                Organization.deleted_at.is_(None),
            )
        )
        projects = await self.session.execute(
            select(ProjectMember.project_id, ProjectMember.role)
            .join(Project, Project.id == ProjectMember.project_id)
            .join(Organization, Organization.id == Project.organization_id)
            .join(
                OrganizationMember,
                (OrganizationMember.organization_id == Organization.id)
                & (OrganizationMember.user_id == ProjectMember.user_id),
            )
            .where(
                ProjectMember.user_id == user_id,
                ProjectMember.state == "active",
                OrganizationMember.state == "active",
                Project.deleted_at.is_(None),
                Organization.deleted_at.is_(None),
            )
        )
        return (
            {identifier: role for identifier, role in organizations},
            {identifier: role for identifier, role in projects},
        )

    async def revoke_memberships(self, user_id: UUID) -> None:
        for model in (OrganizationMember, ProjectMember):
            await self.session.execute(
                update(model).where(model.user_id == user_id).values(state="revoked", role="member")
            )

    async def users_page(
        self, query: str, state: str, after: UUID | None, limit: int
    ) -> list[User]:
        statement = select(User).join(UserProfile).options(selectinload(User.profile))
        if query:
            statement = statement.where(
                (UserProfile.first_name + " " + UserProfile.last_name).icontains(
                    query, autoescape=True
                )
            )
        if state != "all":
            statement = statement.where(User.is_active.is_(state == "active"))
        if after is not None:
            statement = statement.where(User.id > after)
        return list(await self.session.scalars(statement.order_by(User.id).limit(limit + 1)))
