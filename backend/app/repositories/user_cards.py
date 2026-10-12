from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Organization, OrganizationMember, Project, ProjectMember, User
from app.repositories.task_access import organization_visibility, project_visibility
from app.schemas.user_cards import UserMembershipSummary


class UserCardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def memberships(
        self,
        actor_id: UUID,
        target_id: UUID,
        scope: Literal["organizations", "projects"],
        after: UUID | None,
        limit: int,
    ) -> list[UserMembershipSummary]:
        member = aliased(OrganizationMember)
        active_user = select(User.id).where(User.id == target_id, User.is_active.is_(True)).exists()
        if scope == "organizations":
            query = (
                select(
                    Organization.id,
                    Organization.name,
                    member.role,
                    organization_visibility(actor_id).label("can_open"),
                )
                .join(member, member.organization_id == Organization.id)
                .where(
                    member.user_id == target_id,
                    member.state == "active",
                    Organization.archived_at.is_(None),
                    active_user,
                )
            )
            if after is not None:
                query = query.where(Organization.id > after)
            rows = await self.session.execute(query.order_by(Organization.id).limit(limit + 1))
        else:
            project_member = aliased(ProjectMember)
            project_query = (
                select(
                    Project.id,
                    Project.name,
                    project_member.role,
                    project_visibility(actor_id).label("can_open"),
                    Organization.id.label("organization_id"),
                    Organization.name.label("organization_name"),
                )
                .join(Organization, Organization.id == Project.organization_id)
                .join(project_member, project_member.project_id == Project.id)
                .join(
                    member,
                    (member.organization_id == Organization.id) & (member.user_id == target_id),
                )
                .where(
                    project_member.user_id == target_id,
                    project_member.state == "active",
                    member.state == "active",
                    Organization.archived_at.is_(None),
                    Project.archived_at.is_(None),
                    active_user,
                )
            )
            if after is not None:
                project_query = project_query.where(Project.id > after)
            rows = await self.session.execute(project_query.order_by(Project.id).limit(limit + 1))
        return [UserMembershipSummary.model_validate(dict(row)) for row in rows.mappings()]
