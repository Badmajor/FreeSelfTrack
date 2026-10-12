"""Persistence for atomic archive cascades; caller holds lifecycle lock."""

from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OrganizationMember, Project, ProjectMember, Task


class ArchiveRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def projects(self, organization_id: UUID) -> list[Project]:
        return list(
            await self.session.scalars(
                select(Project)
                .where(Project.organization_id == organization_id)
                .order_by(Project.id)
            )
        )

    async def tasks(self, project_ids: list[UUID]) -> list[Task]:
        return list(
            await self.session.scalars(
                select(Task)
                .where(Task.project_id.in_(project_ids), Task.archived_at.is_(None))
                .order_by(Task.id)
            )
        )

    async def memberships(
        self, organization_id: UUID | None, project_ids: list[UUID], *, restore: bool
    ) -> None:
        values = {"state": "revoked", "role": "member"} if restore else {"state": "archived"}
        if organization_id is not None:
            query = update(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id
            )
            if not restore:
                query = query.where(OrganizationMember.state == "active")
            await self.session.execute(query.values(**values))
        query = update(ProjectMember).where(ProjectMember.project_id.in_(project_ids))
        if not restore:
            query = query.where(ProjectMember.state == "active")
        await self.session.execute(query.values(**values))

    async def page(
        self,
        scope: str,
        user_id: UUID,
        parent_id: UUID | None,
        state: str,
        after: UUID | None,
        limit: int,
    ) -> list[Organization | Project | Task]:
        from app.repositories.task_access import (
            organization_visibility,
            project_visibility,
            task_visibility,
        )

        query: Select[Organization] | Select[Project] | Select[Task]
        model: type[Organization] | type[Project] | type[Task]
        if scope == "organization":
            query = select(Organization).where(organization_visibility(user_id))
            model = Organization
        elif scope == "project":
            query = select(Project).where(
                Project.organization_id == parent_id, project_visibility(user_id)
            )
            model = Project
        else:
            query = (
                select(Task)
                .join(Project)
                .where(Task.project_id == parent_id, task_visibility(user_id))
            )
            model = Task
        if state != "all":
            query = query.where(
                model.archived_at.is_(None) if state == "active" else model.archived_at.is_not(None)
            )
        if after is not None:
            query = query.where(model.id > after)
        return list(await self.session.scalars(query.order_by(model.id).limit(limit + 1)))
