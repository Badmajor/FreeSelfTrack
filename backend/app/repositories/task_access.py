"""SQL read scopes shared by resource, candidate and notification queries."""

from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased, selectinload
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    Organization,
    OrganizationMember,
    Project,
    ProjectMember,
    Task,
    User,
    UserProfile,
)


def organization_visibility(user_id: UUID) -> ColumnElement[bool]:
    grant_org = aliased(Organization)
    managers = (
        select(OrganizationMember.user_id)
        .join(grant_org, grant_org.id == OrganizationMember.organization_id)
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.role == "manager",
            or_(
                and_(OrganizationMember.state == "active", grant_org.archived_at.is_(None)),
                and_(OrganizationMember.state == "archived", Organization.archived_at.is_not(None)),
            ),
        )
        .exists()
    )
    member = exists().where(
        OrganizationMember.organization_id == Organization.id,
        OrganizationMember.user_id == user_id,
        or_(
            OrganizationMember.state == "active",
            and_(OrganizationMember.state == "archived", Organization.archived_at.is_not(None)),
        ),
    )
    return and_(
        exists().where(User.id == user_id, User.is_active.is_(True)),
        or_(exists().where(User.id == user_id, User.is_system_admin.is_(True)), managers, member),
    )


def project_visibility(
    user_id: UUID | InstrumentedAttribute[UUID | None],
    *,
    archived: ColumnElement[bool] | None = None,
) -> ColumnElement[bool]:
    """Independent active grants plus retained grants restricted to archived objects."""
    archived = Project.archived_at.is_not(None) if archived is None else archived
    actor = aliased(User)
    grant_org = aliased(Organization)
    grant_project = aliased(Project)
    grant_member = aliased(OrganizationMember)
    org_member = (
        exists()
        .correlate_except(OrganizationMember)
        .where(
            OrganizationMember.organization_id == Project.organization_id,
            OrganizationMember.user_id == user_id,
            or_(
                OrganizationMember.state == "active",
                and_(archived, OrganizationMember.state == "archived"),
            ),
        )
    )
    member = (
        exists()
        .correlate_except(ProjectMember)
        .where(
            ProjectMember.project_id == Project.id,
            ProjectMember.user_id == user_id,
            or_(ProjectMember.state == "active", and_(archived, ProjectMember.state == "archived")),
        )
    )
    managers = (
        select(OrganizationMember.user_id)
        .join(grant_org, grant_org.id == OrganizationMember.organization_id)
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.role == "manager",
            or_(
                and_(OrganizationMember.state == "active", grant_org.archived_at.is_(None)),
                and_(archived, OrganizationMember.state == "archived"),
            ),
        )
        .correlate_except(OrganizationMember, grant_org)
        .exists()
    )
    project_manager = (
        select(ProjectMember.user_id)
        .join(grant_project, grant_project.id == ProjectMember.project_id)
        .join(
            grant_member,
            and_(
                grant_member.organization_id == grant_project.organization_id,
                grant_member.user_id == ProjectMember.user_id,
            ),
        )
        .where(
            ProjectMember.user_id == user_id,
            ProjectMember.role == "manager",
            grant_project.organization_id == Project.organization_id,
            or_(
                and_(
                    ProjectMember.state == "active",
                    grant_member.state == "active",
                    grant_project.archived_at.is_(None),
                ),
                and_(
                    archived,
                    ProjectMember.state == "archived",
                    grant_member.state.in_(("active", "archived")),
                ),
            ),
        )
        .correlate_except(ProjectMember, grant_project, grant_member)
        .exists()
    )
    return and_(
        exists().correlate_except(actor).where(actor.id == user_id, actor.is_active.is_(True)),
        or_(
            exists()
            .correlate_except(actor)
            .where(actor.id == user_id, actor.is_system_admin.is_(True)),
            managers,
            and_(org_member, or_(member, project_manager)),
        ),
    )


def task_visibility(user_id: UUID) -> ColumnElement[bool]:
    return project_visibility(user_id, archived=Task.archived_at.is_not(None))


def project_editability(user_id: UUID) -> ColumnElement[bool]:
    organization = aliased(Organization)
    actor = aliased(User)
    organization_member = exists().where(
        OrganizationMember.organization_id == Project.organization_id,
        OrganizationMember.user_id == user_id,
        OrganizationMember.state == "active",
    )
    organization_manager = exists().where(
        OrganizationMember.organization_id == Project.organization_id,
        OrganizationMember.user_id == user_id,
        OrganizationMember.state == "active",
        OrganizationMember.role == "manager",
    )
    project_member = exists().where(
        ProjectMember.project_id == Project.id,
        ProjectMember.user_id == user_id,
        ProjectMember.state == "active",
    )
    return and_(
        exists().where(actor.id == user_id, actor.is_active.is_(True)),
        Project.archived_at.is_(None),
        exists().where(
            organization.id == Project.organization_id, organization.archived_at.is_(None)
        ),
        or_(
            exists().where(actor.id == user_id, actor.is_system_admin.is_(True)),
            organization_manager,
            and_(organization_member, project_member),
        ),
    )


class TaskAccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def editable_projects(self, user_id: UUID, organization_id: UUID) -> set[UUID]:
        return set(
            await self.session.scalars(
                select(Project.id).where(
                    Project.organization_id == organization_id, project_editability(user_id)
                )
            )
        )

    async def can_read_project(self, user_id: UUID, project_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(Project.id).where(Project.id == project_id, project_visibility(user_id))
            )
            is not None
        )

    async def can_read_task(self, user_id: UUID, task_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(Task.id).join(Project).where(Task.id == task_id, task_visibility(user_id))
            )
            is not None
        )

    @staticmethod
    def readers(project_id: UUID) -> Select[UUID]:
        organization_id = (
            select(Project.organization_id).where(Project.id == project_id).scalar_subquery()
        )
        active_project = (
            select(Project.id)
            .join(Organization)
            .where(
                Project.id == project_id,
                Project.archived_at.is_(None),
                Organization.archived_at.is_(None),
            )
            .exists()
        )
        org_members = select(OrganizationMember.user_id).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.state == "active",
        )
        project_members = select(ProjectMember.user_id).where(
            ProjectMember.project_id == project_id, ProjectMember.state == "active"
        )
        org_managers = (
            select(OrganizationMember.user_id)
            .join(Organization)
            .where(
                OrganizationMember.state == "active",
                OrganizationMember.role == "manager",
                Organization.archived_at.is_(None),
            )
        )
        project_managers = (
            select(ProjectMember.user_id)
            .join(Project)
            .where(
                Project.organization_id == organization_id,
                Project.archived_at.is_(None),
                ProjectMember.state == "active",
                ProjectMember.role == "manager",
            )
        )
        return select(User.id).where(
            active_project,
            User.is_active.is_(True),
            or_(
                User.is_system_admin.is_(True),
                User.id.in_(org_managers),
                and_(
                    User.id.in_(org_members),
                    or_(User.id.in_(project_members), User.id.in_(project_managers)),
                ),
            ),
        )

    async def reader_ids(self, project_id: UUID, candidates: set[UUID] | None = None) -> set[UUID]:
        statement = self.readers(project_id)
        if candidates is not None:
            statement = statement.where(User.id.in_(candidates))
        return set(await self.session.scalars(statement))

    async def candidates(
        self, project_id: UUID, kind: str, query: str, after: UUID | None, limit: int
    ) -> list[User]:
        statement = (
            select(User)
            .join(UserProfile)
            .options(selectinload(User.profile))
            .where(User.is_active.is_(True))
        )
        if kind in {"reporter", "assignee"}:
            statement = statement.where(
                User.id.in_(
                    select(ProjectMember.user_id)
                    .join(Project)
                    .join(
                        OrganizationMember,
                        (OrganizationMember.organization_id == Project.organization_id)
                        & (OrganizationMember.user_id == ProjectMember.user_id),
                    )
                    .where(
                        Project.id == project_id,
                        ProjectMember.state == "active",
                        OrganizationMember.state == "active",
                    )
                )
            )
        else:
            statement = statement.where(User.id.in_(self.readers(project_id)))
        if query:
            statement = statement.where(
                (UserProfile.first_name + " " + UserProfile.last_name).icontains(
                    query, autoescape=True
                )
            )
        if after is not None:
            statement = statement.where(User.id > after)
        return list(await self.session.scalars(statement.order_by(User.id).limit(limit + 1)))
