from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Organization,
    OrganizationMember,
    Project,
    ProjectMember,
    ProjectStatus,
    Task,
    User,
)


class DomainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def get_project(self, project_id: UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_status(self, status_id: UUID) -> ProjectStatus | None:
        return await self.session.get(ProjectStatus, status_id)

    async def get_task(self, task_id: UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def list_organizations_for_user(self, user_id: UUID) -> list[Organization]:
        result = await self.session.scalars(
            select(Organization)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.name)
        )
        return list(result)

    async def list_statuses(self, project_id: UUID) -> list[ProjectStatus]:
        result = await self.session.scalars(
            select(ProjectStatus)
            .where(ProjectStatus.project_id == project_id)
            .order_by(ProjectStatus.position)
        )
        return list(result)

    async def has_organization_access(self, organization_id: UUID, user_id: UUID) -> bool:
        result = await self.session.scalar(
            select(OrganizationMember.organization_id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result is not None

    async def has_project_access(self, project_id: UUID, user_id: UUID) -> bool:
        result = await self.session.scalar(
            select(ProjectMember.project_id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        return result is not None

    async def add_organization_member(self, organization_id: UUID, user_id: UUID) -> None:
        self.session.add(OrganizationMember(organization_id=organization_id, user_id=user_id))

    async def add_project_member(self, project_id: UUID, user_id: UUID) -> None:
        self.session.add(ProjectMember(project_id=project_id, user_id=user_id))
