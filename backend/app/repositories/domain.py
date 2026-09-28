from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Notification,
    Organization,
    OrganizationMember,
    Project,
    ProjectMember,
    ProjectStatus,
    Task,
    TaskHistory,
    TaskWatcher,
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
            .where(
                OrganizationMember.user_id == user_id,
                Organization.deleted_at.is_(None),
            )
            .order_by(Organization.name)
        )
        return list(result)

    async def list_projects_for_organization(self, organization_id: UUID) -> list[Project]:
        result = await self.session.scalars(
            select(Project)
            .where(
                Project.organization_id == organization_id,
                Project.deleted_at.is_(None),
            )
            .order_by(Project.name)
        )
        return list(result)

    async def list_organization_members(self, organization_id: UUID) -> list[User]:
        result = await self.session.scalars(
            select(User)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.email)
        )
        return list(result)

    async def list_project_members(self, project_id: UUID) -> list[User]:
        result = await self.session.scalars(
            select(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
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
        result = await self.session.scalar(
            select(OrganizationMember.organization_id)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
                Organization.deleted_at.is_(None),
            )
        )
        return result is not None

    async def has_project_access(self, project_id: UUID, user_id: UUID) -> bool:
        result = await self.session.scalar(
            select(ProjectMember.project_id)
            .join(Project, Project.id == ProjectMember.project_id)
            .join(Organization, Organization.id == Project.organization_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                Project.deleted_at.is_(None),
                Organization.deleted_at.is_(None),
            )
        )
        return result is not None

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
            await self.session.delete(member)

    async def remove_project_member(self, project_id: UUID, user_id: UUID) -> None:
        member = await self.get_project_member(project_id, user_id)
        if member is not None:
            await self.session.delete(member)

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
    ) -> list[Task]:
        query = select(Task).where(Task.project_id == project_id, Task.status_id == status_id)
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

    async def list_task_history(
        self, task_id: UUID, limit: int, cursor: tuple[object, UUID] | None = None
    ) -> list[TaskHistory]:
        query = select(TaskHistory).where(TaskHistory.task_id == task_id)
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

    async def get_notification(self, notification_id: UUID) -> Notification | None:
        return await self.session.get(Notification, notification_id)

    async def list_notifications(self, user_id: UUID, limit: int = 100) -> list[Notification]:
        result = await self.session.scalars(
            select(Notification)
            .where(Notification.recipient_id == user_id)
            .order_by(desc(Notification.created_at), desc(Notification.id))
            .limit(limit)
        )
        return list(result)

    async def count_unread_notifications(self, user_id: UUID) -> int:
        count = await self.session.scalar(
            select(func.count(Notification.id)).where(
                Notification.recipient_id == user_id, Notification.read_at.is_(None)
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
