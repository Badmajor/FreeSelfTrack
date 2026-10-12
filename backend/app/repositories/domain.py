from datetime import date
from uuid import UUID

from sqlalchemy import (
    JSON,
    String,
    and_,
    cast,
    desc,
    exists,
    func,
    literal,
    or_,
    select,
    true,
    type_coerce,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    DeadlineNotificationDelivery,
    Notification,
    Organization,
    OrganizationMember,
    Project,
    ProjectMember,
    ProjectStatus,
    ProjectTaskSequence,
    Task,
    TaskHistory,
    TaskLink,
    TaskWatcher,
    User,
)
from app.repositories.task_access import (
    organization_visibility,
    project_editability,
    project_visibility,
    task_visibility,
)


class DomainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.scalar(
            select(User).options(selectinload(User.profile)).where(User.id == user_id)
        )

    async def get_user_by_email(self, email: str) -> User | None:
        return await self.session.scalar(
            select(User).options(selectinload(User.profile)).where(User.email == email)
        )

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id, populate_existing=True)

    async def organizations_by_ids(self, ids: set[UUID]) -> dict[UUID, Organization]:
        rows = await self.session.scalars(select(Organization).where(Organization.id.in_(ids)))
        return {row.id: row for row in rows}

    async def get_project(self, project_id: UUID) -> Project | None:
        return await self.session.get(Project, project_id, populate_existing=True)

    async def get_status(self, status_id: UUID) -> ProjectStatus | None:
        return await self.session.get(ProjectStatus, status_id)

    async def get_task(self, task_id: UUID) -> Task | None:
        return await self.session.scalar(
            select(Task)
            .options(selectinload(Task.assignee).selectinload(User.profile))
            .where(Task.id == task_id)
            .execution_options(populate_existing=True)
        )

    async def list_due_tasks(self, current_date: date, limit: int) -> list[Task]:
        delivered = exists().where(
            DeadlineNotificationDelivery.task_id == Task.id,
            DeadlineNotificationDelivery.due_date == Task.due_date,
            DeadlineNotificationDelivery.recipient_id == Task.assignee_id,
        )
        result = await self.session.scalars(
            select(Task)
            .join(ProjectStatus, ProjectStatus.id == Task.status_id)
            .join(Project, Project.id == Task.project_id)
            .join(Organization, Organization.id == Project.organization_id)
            .join(User, User.id == Task.assignee_id)
            .where(
                Task.archived_at.is_(None),
                Task.due_date.is_not(None),
                Task.due_date <= current_date,
                Task.assignee_id.is_not(None),
                ProjectStatus.is_completed.is_(False),
                Project.archived_at.is_(None),
                Organization.archived_at.is_(None),
                User.is_active.is_(True),
                project_visibility(Task.assignee_id),
                ~delivered,
            )
            .order_by(Task.due_date, Task.id)
            .limit(limit)
            .with_for_update(skip_locked=True, of=Task)
        )
        return list(result)

    async def get_project_task_sequence(self, project_id: UUID) -> ProjectTaskSequence | None:
        return await self.session.scalar(
            select(ProjectTaskSequence)
            .where(ProjectTaskSequence.project_id == project_id)
            .with_for_update()
        )

    async def list_organizations_for_user(self, user_id: UUID) -> list[Organization]:
        return list(
            await self.session.scalars(
                select(Organization)
                .where(organization_visibility(user_id))
                .order_by(Organization.name)
            )
        )

    async def list_projects_for_organization(self, organization_id: UUID) -> list[Project]:
        result = await self.session.scalars(
            select(Project)
            .where(
                Project.organization_id == organization_id,
                Project.archived_at.is_(None),
            )
            .order_by(Project.name)
        )
        return list(result)

    async def list_projects_for_user(self, organization_id: UUID, user_id: UUID) -> list[Project]:
        return list(
            await self.session.scalars(
                select(Project)
                .where(Project.organization_id == organization_id, project_visibility(user_id))
                .order_by(Project.name)
            )
        )

    async def list_organization_members(self, organization_id: UUID) -> list[User]:
        result = await self.session.scalars(
            select(User)
            .options(selectinload(User.profile))
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.state == "active",
                User.is_active.is_(True),
            )
            .order_by(User.email)
        )
        return list(result)

    async def list_project_members(self, project_id: UUID) -> list[User]:
        result = await self.session.scalars(
            select(User)
            .options(selectinload(User.profile))
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.state == "active",
                User.is_active.is_(True),
            )
            .order_by(User.email)
        )
        return list(result)

    async def get_organization_member(
        self, organization_id: UUID, user_id: UUID
    ) -> OrganizationMember | None:
        return await self.session.get(
            OrganizationMember, {"organization_id": organization_id, "user_id": user_id}
        )

    async def get_project_member(self, project_id: UUID, user_id: UUID) -> ProjectMember | None:
        return await self.session.get(ProjectMember, {"project_id": project_id, "user_id": user_id})

    async def has_organization_access(self, organization_id: UUID, user_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(Organization.id).where(
                    Organization.id == organization_id, organization_visibility(user_id)
                )
            )
            is not None
        )

    async def has_project_access(self, project_id: UUID, user_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(Project.id).where(Project.id == project_id, project_editability(user_id))
            )
            is not None
        )

    async def add_organization_member(
        self, organization_id: UUID, user_id: UUID
    ) -> OrganizationMember:
        member = await self.get_organization_member(organization_id, user_id)
        if member is None:
            member = OrganizationMember(organization_id=organization_id, user_id=user_id)
            self.session.add(member)
        return member

    async def add_project_member(self, project_id: UUID, user_id: UUID) -> ProjectMember:
        member = await self.get_project_member(project_id, user_id)
        if member is None:
            member = ProjectMember(project_id=project_id, user_id=user_id)
            self.session.add(member)
        return member

    async def remove_organization_member(self, organization_id: UUID, user_id: UUID) -> None:
        member = await self.get_organization_member(organization_id, user_id)
        if member is not None:
            member.state = "revoked"
            member.role = "member"

        await self.session.execute(
            update(ProjectMember)
            .where(
                ProjectMember.user_id == user_id,
                ProjectMember.project_id.in_(
                    select(Project.id).where(Project.organization_id == organization_id)
                ),
            )
            .values(state="revoked", role="member")
        )

    async def remove_project_member(self, project_id: UUID, user_id: UUID) -> None:
        member = await self.get_project_member(project_id, user_id)
        if member is not None:
            member.state = "revoked"
            member.role = "member"

    async def list_statuses(self, project_id: UUID) -> list[ProjectStatus]:
        result = await self.session.scalars(
            select(ProjectStatus)
            .where(ProjectStatus.project_id == project_id, ProjectStatus.is_active.is_(True))
            .order_by(ProjectStatus.position)
        )
        return list(result)

    async def list_archived_statuses(self, project_id: UUID) -> list[ProjectStatus]:
        result = await self.session.scalars(
            select(ProjectStatus)
            .where(ProjectStatus.project_id == project_id, ProjectStatus.is_active.is_(False))
            .order_by(ProjectStatus.position)
        )
        return list(result)

    async def list_tasks_for_status(
        self,
        project_id: UUID,
        status_id: UUID,
        limit: int,
        cursor: tuple[object, UUID] | None = None,
        *,
        state: str = "active",
        user_id: UUID,
    ) -> list[Task]:
        query = (
            select(Task)
            .join(Project)
            .where(Task.project_id == project_id, Task.status_id == status_id)
        )
        query = query.where(task_visibility(user_id))
        if state != "all":
            query = query.where(
                Task.archived_at.is_(None) if state == "active" else Task.archived_at.is_not(None)
            )
        if cursor is not None:
            timestamp, item_id = cursor
            query = query.where(
                or_(
                    Task.updated_at < timestamp,
                    and_(Task.updated_at == timestamp, Task.id < item_id),
                )
            )
        result = await self.session.scalars(
            query.order_by(desc(Task.updated_at), desc(Task.id)).limit(limit + 1)
        )
        return list(result)

    async def has_tasks_for_status(self, status_id: UUID) -> bool:
        return (
            await self.session.scalar(select(Task.id).where(Task.status_id == status_id).limit(1))
        ) is not None

    async def get_task_link(self, link_id: UUID) -> TaskLink | None:
        return await self.session.scalar(
            select(TaskLink)
            .options(selectinload(TaskLink.creator).selectinload(User.profile))
            .where(TaskLink.id == link_id)
        )

    async def lock_task_pair(self, task_a_id: UUID, task_b_id: UUID) -> None:
        await self.session.execute(
            select(Task.id)
            .where(Task.id.in_((task_a_id, task_b_id)))
            .order_by(Task.id)
            .with_for_update()
        )

    async def get_task_link_pair(self, task_a_id: UUID, task_b_id: UUID) -> TaskLink | None:
        return await self.session.scalar(
            select(TaskLink)
            .options(selectinload(TaskLink.creator).selectinload(User.profile))
            .where(TaskLink.task_a_id == task_a_id, TaskLink.task_b_id == task_b_id)
        )

    async def list_task_links(self, task_id: UUID, user_id: UUID) -> list[TaskLink]:
        visible_tasks = select(Task.id).join(Project).where(task_visibility(user_id))
        result = await self.session.scalars(
            select(TaskLink)
            .options(selectinload(TaskLink.creator).selectinload(User.profile))
            .where(
                or_(TaskLink.task_a_id == task_id, TaskLink.task_b_id == task_id),
                TaskLink.task_a_id.in_(visible_tasks),
                TaskLink.task_b_id.in_(visible_tasks),
            )
            .order_by(TaskLink.created_at, TaskLink.id)
        )
        return list(result)

    async def search_organization_tasks(
        self, organization_id: UUID, slug: str, limit: int, user_id: UUID, state: str = "active"
    ) -> list[tuple[Task, Project, ProjectStatus]]:
        rows = await self.session.execute(
            select(Task, Project, ProjectStatus)
            .join(Project, Project.id == Task.project_id)
            .join(Organization, Organization.id == Project.organization_id)
            .join(ProjectStatus, ProjectStatus.id == Task.status_id)
            .where(
                Project.organization_id == organization_id,
                task_visibility(user_id),
                true()
                if state == "all"
                else Task.archived_at.is_(None)
                if state == "active"
                else Task.archived_at.is_not(None),
                func.lower(Task.slug).startswith(slug.casefold(), autoescape=True),
            )
            .order_by(Project.name, Task.id)
            .limit(limit)
        )
        return [(task, project, status) for task, project, status in rows]

    async def list_task_history(
        self, task_id: UUID, limit: int, cursor: tuple[object, UUID] | None = None, *, user_id: UUID
    ) -> list[TaskHistory]:
        # Legacy link history stores a slug/title snapshot, not a target UUID. Match in
        # the source organization and hide ambiguous snapshots if any match is inaccessible.
        linked = aliased(Task)
        source_project = aliased(Project)
        source = aliased(Task)
        organization_id = (
            select(source_project.organization_id)
            .join(source, source.project_id == source_project.id)
            .where(source.id == task_id)
            .scalar_subquery()
        )
        snapshot = func.coalesce(TaskHistory.new_value, TaskHistory.old_value)
        prefixes = [
            literal(relation + ": ") + linked.slug + literal(" ")
            for relation in ("blocks", "depends_on", "related")
        ]
        match = (
            select(linked.id)
            .join(Project, Project.id == linked.project_id)
            .where(
                Project.organization_id == organization_id,
                linked.id != task_id,
                or_(
                    *(
                        func.substr(snapshot, 1, func.length(prefix)) == prefix
                        for prefix in prefixes
                    )
                ),
            )
            .correlate(TaskHistory)
        )
        visible = or_(
            TaskHistory.event_type.not_in(("task_link_added", "task_link_removed")),
            and_(
                match.where(
                    project_visibility(user_id, archived=linked.archived_at.is_not(None))
                ).exists(),
                ~match.where(
                    ~project_visibility(user_id, archived=linked.archived_at.is_not(None))
                ).exists(),
            ),
        )
        query = (
            select(TaskHistory)
            .options(selectinload(TaskHistory.actor).selectinload(User.profile))
            .where(TaskHistory.task_id == task_id, visible)
        )
        if cursor is not None:
            timestamp, item_id = cursor
            query = query.where(
                or_(
                    TaskHistory.created_at < timestamp,
                    and_(TaskHistory.created_at == timestamp, TaskHistory.id < item_id),
                )
            )
        result = await self.session.scalars(
            query.order_by(desc(TaskHistory.created_at), desc(TaskHistory.id)).limit(limit + 1)
        )
        return list(result)

    async def has_active_project_access(self, project_id: UUID, user_id: UUID) -> bool:
        return await self.has_project_access(project_id, user_id)

    async def list_task_watchers(self, task_id: UUID) -> list[User]:
        result = await self.session.scalars(
            select(User)
            .options(selectinload(User.profile))
            .join(TaskWatcher, TaskWatcher.user_id == User.id)
            .where(TaskWatcher.task_id == task_id)
            .order_by(User.email)
        )
        return list(result)

    async def list_task_watcher_ids(self, task_id: UUID) -> list[UUID]:
        result = await self.session.scalars(
            select(TaskWatcher.user_id).where(TaskWatcher.task_id == task_id)
        )
        return list(result)

    async def get_task_watcher(self, task_id: UUID, user_id: UUID) -> TaskWatcher | None:
        return await self.session.get(TaskWatcher, {"task_id": task_id, "user_id": user_id})

    async def add_task_watcher(self, task_id: UUID, user_id: UUID) -> TaskWatcher:
        watcher = await self.get_task_watcher(task_id, user_id)
        if watcher is None:
            watcher = TaskWatcher(task_id=task_id, user_id=user_id)
            self.session.add(watcher)
        return watcher

    async def remove_task_watcher(self, task_id: UUID, user_id: UUID) -> None:
        watcher = await self.get_task_watcher(task_id, user_id)
        if watcher is not None:
            await self.session.delete(watcher)

    async def get_notification(self, notification_id: UUID, user_id: UUID) -> Notification | None:
        return await self.session.scalar(
            select(Notification)
            .join(Task)
            .join(Project)
            .where(
                Notification.id == notification_id,
                Notification.recipient_id == user_id,
                self.notification_visibility(user_id),
            )
        )

    def notification_visibility(self, user_id: UUID) -> ColumnElement[bool]:
        linked = aliased(Task)
        payload = (
            cast(Notification.event_data, JSON)
            if self.session.get_bind().dialect.name == "postgresql"
            else type_coerce(Notification.event_data, JSON)
        )
        linked_id = payload["linked_task_id"].as_string()
        linked_visible = (
            select(linked.id)
            .join(Project, Project.id == linked.project_id)
            .where(
                func.replace(cast(linked.id, String), "-", "") == func.replace(linked_id, "-", ""),
                project_visibility(user_id, archived=linked.archived_at.is_not(None)),
            )
            .correlate(Notification)
            .exists()
        )
        return and_(
            task_visibility(user_id),
            or_(
                Notification.event_type.not_in(("task_link_added", "task_link_removed")),
                linked_visible,
            ),
        )

    async def list_notifications(self, user_id: UUID, limit: int = 100) -> list[Notification]:
        result = await self.session.scalars(
            select(Notification)
            .join(Task, Task.id == Notification.task_id)
            .join(Project, Project.id == Task.project_id)
            .where(Notification.recipient_id == user_id, self.notification_visibility(user_id))
            .order_by(desc(Notification.created_at), desc(Notification.id))
            .limit(limit)
        )
        return list(result)

    async def count_unread_notifications(self, user_id: UUID) -> int:
        count = await self.session.scalar(
            select(func.count(Notification.id))
            .join(Task, Task.id == Notification.task_id)
            .join(Project, Project.id == Task.project_id)
            .where(
                self.notification_visibility(user_id),
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        return int(count or 0)

    def add_notification(
        self,
        recipient_id: UUID,
        task_id: UUID,
        event_type: str,
        message: str,
        event_data: str | None = None,
    ) -> Notification:
        notification = Notification(
            recipient_id=recipient_id,
            task_id=task_id,
            event_type=event_type,
            message=message,
            event_data=event_data,
        )
        self.session.add(notification)
        return notification
