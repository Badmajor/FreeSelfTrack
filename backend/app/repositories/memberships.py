from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import OrganizationMember, Project, ProjectMember, Task, User

Scope = Literal["organization", "project"]
Membership = OrganizationMember | ProjectMember


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def page(
        self, scope: Scope, scope_id: UUID, state: str, after: UUID | None, limit: int
    ) -> list[tuple[Membership, User]]:
        model = OrganizationMember if scope == "organization" else ProjectMember
        parent = (
            OrganizationMember.organization_id
            if scope == "organization"
            else ProjectMember.project_id
        )
        statement = (
            select(model, User)
            .join(User, User.id == model.user_id)
            .options(selectinload(User.profile))
            .where(parent == scope_id, model.state == state)
            .order_by(model.user_id)
            .limit(limit + 1)
        )
        if state == "active":
            statement = statement.where(User.is_active.is_(True))
            if scope == "project":
                statement = (
                    statement.join(Project, Project.id == ProjectMember.project_id)
                    .join(
                        OrganizationMember,
                        (OrganizationMember.organization_id == Project.organization_id)
                        & (OrganizationMember.user_id == User.id),
                    )
                    .where(OrganizationMember.state == "active")
                )
        if after is not None:
            statement = statement.where(model.user_id > after)
        rows = []
        for member, user in await self.session.execute(statement):
            assert isinstance(member, (OrganizationMember, ProjectMember))
            rows.append((member, user))
        return rows

    async def assignee_states(
        self, task_ids: list[UUID]
    ) -> dict[UUID, tuple[bool, str | None, str | None]]:
        rows = await self.session.execute(
            select(Task.id, User.is_active, OrganizationMember.state, ProjectMember.state)
            .join(Project, Project.id == Task.project_id)
            .join(User, User.id == Task.assignee_id)
            .outerjoin(
                OrganizationMember,
                (OrganizationMember.organization_id == Project.organization_id)
                & (OrganizationMember.user_id == User.id),
            )
            .outerjoin(
                ProjectMember,
                (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == User.id),
            )
            .where(Task.id.in_(task_ids))
        )
        return {
            task_id: (active, organization_state, project_state)
            for task_id, active, organization_state, project_state in rows
        }
