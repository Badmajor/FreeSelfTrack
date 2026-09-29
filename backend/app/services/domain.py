import binascii
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cursor import decode_cursor, encode_cursor
from app.models import Organization, Project, ProjectStatus, Task, TaskHistory, User
from app.repositories.domain import DomainRepository
from app.schemas.domain import (
    BoardColumnResponse,
    BoardResponse,
    ConfirmRequest,
    MembershipRequest,
    NotificationResponse,
    OrganizationCreate,
    ProfileResponse,
    ProjectCreate,
    ProjectUpdate,
    StatusCreate,
    StatusReorder,
    StatusResponse,
    StatusUpdate,
    TaskCreate,
    TaskHistoryPageResponse,
    TaskHistoryResponse,
    TaskPageResponse,
    TaskResponse,
    TaskUpdate,
    UnreadCountResponse,
    UserSummary,
    WatcherRequest,
)
from app.services.errors import (
    ConflictError,
    InvalidWorkflowError,
    NotFoundError,
    PermissionDeniedError,
)

DEFAULT_STATUSES = ("Backlog", "In Progress", "Done")


def normalized_email(email: str) -> str:
    return email.strip().casefold()


class DomainService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DomainRepository(session)

    async def create_organization(self, user_id: UUID, data: OrganizationCreate) -> Organization:
        organization = Organization(owner_id=user_id, name=data.name)
        self.session.add(organization)
        await self.session.flush()
        await self.repository.add_organization_member(organization.id, user_id)
        await self.session.commit()
        return organization

    async def list_organizations(self, user_id: UUID) -> list[Organization]:
        return await self.repository.list_organizations_for_user(user_id)

    async def get_organization(self, user_id: UUID, organization_id: UUID) -> Organization:
        organization = await self.repository.get_organization(organization_id)
        if organization is None or organization.deleted_at is not None:
            raise NotFoundError("Organization not found")
        if not await self.repository.has_organization_access(organization_id, user_id):
            raise NotFoundError("Organization not found")
        return organization

    async def list_projects(self, user_id: UUID, organization_id: UUID) -> list[Project]:
        await self.get_organization(user_id, organization_id)
        return await self.repository.list_projects_for_organization(organization_id)

    async def create_project(self, user_id: UUID, data: ProjectCreate) -> Project:
        await self.get_organization(user_id, data.organization_id)
        project = Project(
            organization_id=data.organization_id,
            owner_id=user_id,
            name=data.name,
        )
        self.session.add(project)
        await self.session.flush()
        await self.repository.add_project_member(project.id, user_id)
        for position, name in enumerate(DEFAULT_STATUSES):
            self.session.add(ProjectStatus(project_id=project.id, name=name, position=position))
        await self.session.commit()
        return project

    async def get_project(self, user_id: UUID, project_id: UUID) -> Project:
        project = await self.repository.get_project(project_id)
        if (
            project is None
            or project.deleted_at is not None
            or not await self.repository.has_project_access(project_id, user_id)
        ):
            raise NotFoundError("Project not found")
        return project

    async def update_project(self, user_id: UUID, project_id: UUID, data: ProjectUpdate) -> Project:
        project = await self.get_project(user_id, project_id)
        if data.name is not None:
            project.name = data.name
        await self.session.commit()
        return project

    async def list_organization_members(self, user_id: UUID, organization_id: UUID) -> list[User]:
        await self.get_organization(user_id, organization_id)
        return await self.repository.list_organization_members(organization_id)

    async def add_organization_member(
        self, user_id: UUID, organization_id: UUID, data: MembershipRequest
    ) -> User:
        organization = await self.get_organization(user_id, organization_id)
        self._require_owner(user_id, organization.owner_id)
        member_user = await self._find_user(data.email)
        await self.repository.add_organization_member(organization_id, member_user.id)
        await self.session.commit()
        return member_user

    async def remove_organization_member(
        self, user_id: UUID, organization_id: UUID, member_id: UUID
    ) -> User:
        organization = await self.get_organization(user_id, organization_id)
        self._require_owner(user_id, organization.owner_id)
        if member_id == organization.owner_id:
            raise ConflictError("Organization owner must transfer ownership first")
        member = await self.repository.get_organization_member(organization_id, member_id)
        if member is None:
            raise NotFoundError("Organization member not found")
        member_user = await self.repository.get_user(member_id)
        if member_user is None:
            raise NotFoundError("Organization member not found")
        await self.repository.remove_organization_member(organization_id, member_id)
        await self.session.commit()
        return member_user

    async def transfer_organization_ownership(
        self, user_id: UUID, organization_id: UUID, data: MembershipRequest
    ) -> Organization:
        organization = await self.get_organization(user_id, organization_id)
        self._require_owner(user_id, organization.owner_id)
        target = await self._find_user(data.email)
        if await self.repository.get_organization_member(organization_id, target.id) is None:
            raise ConflictError("New owner must be an organization member")
        organization.owner_id = target.id
        await self.session.commit()
        return organization

    async def delete_organization(
        self, user_id: UUID, organization_id: UUID, data: ConfirmRequest
    ) -> None:
        organization = await self.get_organization(user_id, organization_id)
        self._require_owner(user_id, organization.owner_id)
        self._require_confirmation(data)
        deleted_at = datetime.now(UTC)
        organization.deleted_at = deleted_at
        projects = await self.repository.list_projects_for_organization(organization_id)
        for project in projects:
            project.deleted_at = deleted_at
        await self.session.commit()

    async def restore_organization(self, user_id: UUID, organization_id: UUID) -> Organization:
        organization = await self._get_deleted_organization(organization_id)
        self._require_owner(user_id, organization.owner_id)
        organization.deleted_at = None
        await self.session.commit()
        return organization

    async def list_project_members(self, user_id: UUID, project_id: UUID) -> list[User]:
        await self.get_project(user_id, project_id)
        return await self.repository.list_project_members(project_id)

    async def add_project_member(
        self, user_id: UUID, project_id: UUID, data: MembershipRequest
    ) -> User:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        member_user = await self._find_user(data.email)
        if not await self.repository.has_organization_access(
            project.organization_id, member_user.id
        ):
            raise ConflictError("Project member must belong to the project organization")
        await self.repository.add_project_member(project_id, member_user.id)
        await self.session.commit()
        return member_user

    async def remove_project_member(self, user_id: UUID, project_id: UUID, member_id: UUID) -> User:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        if member_id == project.owner_id:
            raise ConflictError("Project owner must transfer ownership first")
        member = await self.repository.get_project_member(project_id, member_id)
        if member is None:
            raise NotFoundError("Project member not found")
        member_user = await self.repository.get_user(member_id)
        if member_user is None:
            raise NotFoundError("Project member not found")
        await self.repository.remove_project_member(project_id, member_id)
        await self.session.commit()
        return member_user

    async def transfer_project_ownership(
        self, user_id: UUID, project_id: UUID, data: MembershipRequest
    ) -> Project:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        target = await self._find_user(data.email)
        if await self.repository.get_project_member(project_id, target.id) is None:
            raise ConflictError("New owner must be a project member")
        project.owner_id = target.id
        await self.session.commit()
        return project

    async def delete_project(self, user_id: UUID, project_id: UUID, data: ConfirmRequest) -> None:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        self._require_confirmation(data)
        project.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def restore_project(self, user_id: UUID, project_id: UUID) -> Project:
        project = await self._get_deleted_project(project_id)
        self._require_owner(user_id, project.owner_id)
        organization = await self.repository.get_organization(project.organization_id)
        if organization is None or organization.deleted_at is not None:
            raise ConflictError("Restore the project organization first")
        project.deleted_at = None
        await self.session.commit()
        return project

    async def create_status(
        self, user_id: UUID, project_id: UUID, data: StatusCreate
    ) -> ProjectStatus:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        statuses = await self.repository.list_statuses(project_id)
        position = len(statuses) if data.position is None else min(data.position, len(statuses))
        if not data.is_active:
            archived_statuses = await self.repository.list_archived_statuses(project_id)
            position = -(len(archived_statuses) + 1000)
        project_status = ProjectStatus(
            project_id=project_id, name=data.name, position=position, is_active=data.is_active
        )
        self.session.add(project_status)
        statuses.insert(position, project_status)
        await self._renumber(statuses)
        await self.session.commit()
        return project_status

    async def list_statuses(self, user_id: UUID, project_id: UUID) -> list[ProjectStatus]:
        await self.get_project(user_id, project_id)
        return await self.repository.list_statuses(project_id)

    async def list_archived_statuses(self, user_id: UUID, project_id: UUID) -> list[ProjectStatus]:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        return await self.repository.list_archived_statuses(project_id)

    async def update_status(
        self, user_id: UUID, project_id: UUID, status_id: UUID, data: StatusUpdate
    ) -> ProjectStatus:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        project_status = await self._get_project_status(project_id, status_id)
        if data.is_active is False:
            return await self.archive_status(user_id, project_id, status_id)
        if data.is_active is True and not project_status.is_active:
            return await self.restore_status(user_id, project_id, status_id)
        if data.name is not None:
            project_status.name = data.name
        if data.position is not None and data.position != project_status.position:
            statuses = await self.repository.list_statuses(project_id)
            statuses.remove(project_status)
            statuses.insert(min(data.position, len(statuses)), project_status)
            await self._renumber(statuses)
        await self.session.commit()
        return project_status

    async def reorder_statuses(
        self, user_id: UUID, project_id: UUID, data: StatusReorder
    ) -> list[ProjectStatus]:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        statuses = await self.repository.list_statuses(project_id)
        current_ids = {project_status.id for project_status in statuses}
        if len(data.status_ids) != len(set(data.status_ids)) or set(data.status_ids) != current_ids:
            raise InvalidWorkflowError(
                "status_ids must contain every active project status exactly once"
            )
        by_id = {project_status.id: project_status for project_status in statuses}
        ordered = [by_id[status_id] for status_id in data.status_ids]
        await self._renumber(ordered)
        await self.session.commit()
        return ordered

    async def archive_status(
        self, user_id: UUID, project_id: UUID, status_id: UUID
    ) -> ProjectStatus:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        project_status = await self._get_project_status(project_id, status_id)
        if not project_status.is_active:
            return project_status
        if await self.repository.has_tasks_for_status(status_id):
            raise ConflictError("Move all tasks before archiving this status")
        if len(await self.repository.list_statuses(project_id)) <= 1:
            raise ConflictError("At least one active status must remain")
        project_status.is_active = False
        archived_statuses = await self.repository.list_archived_statuses(project_id)
        project_status.position = -(len(archived_statuses) + 1000)
        await self.session.flush()
        active_statuses = await self.repository.list_statuses(project_id)
        await self._renumber(active_statuses)
        await self.session.commit()
        return project_status

    async def restore_status(
        self, user_id: UUID, project_id: UUID, status_id: UUID
    ) -> ProjectStatus:
        project = await self.get_project(user_id, project_id)
        self._require_owner(user_id, project.owner_id)
        project_status = await self._get_project_status(project_id, status_id)
        if project_status.is_active:
            return project_status
        project_status.is_active = True
        active_statuses = await self.repository.list_statuses(project_id)
        project_status.position = len(active_statuses)
        active_statuses.append(project_status)
        await self._renumber(active_statuses)
        await self.session.commit()
        return project_status

    async def create_task(self, user_id: UUID, project_id: UUID, data: TaskCreate) -> Task:
        project = await self.get_project(user_id, project_id)
        project_status = await self.repository.get_status(data.status_id)
        if (
            project_status is None
            or project_status.project_id != project_id
            or not project_status.is_active
        ):
            raise InvalidWorkflowError("Task status must be an active status of the task project")
        reporter_id = data.reporter_id or user_id
        await self._require_organization_user(project.organization_id, reporter_id)
        if data.assignee_id is not None:
            await self._require_organization_user(project.organization_id, data.assignee_id)
        task = Task(
            project_id=project_id,
            status_id=project_status.id,
            title=data.title,
            description=data.description,
            created_by=user_id,
            reporter_id=reporter_id,
            assignee_id=data.assignee_id,
        )
        self.session.add(task)
        await self.session.commit()
        return task

    async def create_task_response(
        self, user_id: UUID, project_id: UUID, data: TaskCreate
    ) -> TaskResponse:
        task = await self.create_task(user_id, project_id, data)
        return await self._task_response(task)

    async def get_task(self, user_id: UUID, task_id: UUID) -> Task:
        task = await self.repository.get_task(task_id)
        if task is None or not await self.repository.has_project_access(task.project_id, user_id):
            raise NotFoundError("Task not found")
        return task

    async def get_task_response(self, user_id: UUID, task_id: UUID) -> TaskResponse:
        return await self._task_response(await self.get_task(user_id, task_id))

    async def update_task(self, user_id: UUID, task_id: UUID, data: TaskUpdate) -> Task:
        task = await self.get_task(user_id, task_id)
        project = await self.repository.get_project(task.project_id)
        if project is None:
            raise NotFoundError("Task not found")
        events: list[tuple[str, str, dict[str, str]]] = []
        if data.title is not None and data.title != task.title:
            old_value = task.title
            task.title = data.title
            await self._record_history(
                task, user_id, "title_changed", "title", old_value, data.title
            )
            events.append(("title_changed", "Task title changed", {"title": data.title}))
        if "description" in data.model_fields_set and data.description != task.description:
            old_value = task.description
            task.description = data.description
            await self._record_history(
                task, user_id, "description_changed", "description", old_value, data.description
            )
            events.append(("description_changed", "Task description changed", {}))
        if data.status_id is not None and data.status_id != task.status_id:
            project_status = await self.repository.get_status(data.status_id)
            if (
                project_status is None
                or project_status.project_id != task.project_id
                or not project_status.is_active
            ):
                raise InvalidWorkflowError(
                    "Task status must be an active status of the task project"
                )
            old_status = await self.repository.get_status(task.status_id)
            self.session.add(
                TaskHistory(
                    task_id=task.id,
                    changed_by=user_id,
                    from_status_id=task.status_id,
                    to_status_id=project_status.id,
                    event_type="status_changed",
                    field_name="status",
                    old_value=old_status.name if old_status else None,
                    new_value=project_status.name,
                )
            )
            task.status_id = project_status.id
            events.append(
                ("status_changed", "Task status changed", {"status_id": str(project_status.id)})
            )
        if "reporter_id" in data.model_fields_set:
            self._require_reporter_permission(user_id, task, project.owner_id)
            if data.reporter_id is None:
                raise InvalidWorkflowError("A task must have a reporter")
            await self._require_organization_user(project.organization_id, data.reporter_id)
            if data.reporter_id != task.reporter_id:
                old_value = await self._display_name(task.reporter_id)
                new_value = await self._display_name(data.reporter_id)
                task.reporter_id = data.reporter_id
                await self._record_history(
                    task, user_id, "reporter_changed", "reporter", old_value, new_value
                )
                events.append(
                    (
                        "reporter_changed",
                        "Task reporter changed",
                        {"reporter_id": str(data.reporter_id)},
                    )
                )
        if "assignee_id" in data.model_fields_set:
            self._require_assignee_permission(user_id, task, project.owner_id, data.assignee_id)
            if data.assignee_id is not None:
                await self._require_organization_user(project.organization_id, data.assignee_id)
            if data.assignee_id != task.assignee_id:
                old_value = await self._display_name(task.assignee_id) if task.assignee_id else None
                new_value = await self._display_name(data.assignee_id) if data.assignee_id else None
                task.assignee_id = data.assignee_id
                await self._record_history(
                    task, user_id, "assignee_changed", "assignee", old_value, new_value
                )
                events.append(
                    (
                        "assignee_changed",
                        "Task assignee changed",
                        {"assignee_id": str(data.assignee_id) if data.assignee_id else ""},
                    )
                )
        await self._queue_notifications(task, user_id, events)
        await self.session.commit()
        return task

    async def update_task_response(
        self, user_id: UUID, task_id: UUID, data: TaskUpdate
    ) -> TaskResponse:
        return await self._task_response(await self.update_task(user_id, task_id, data))

    async def list_task_watchers(self, user_id: UUID, task_id: UUID) -> list[User]:
        await self.get_task(user_id, task_id)
        return await self.repository.list_task_watchers(task_id)

    async def add_task_watcher(
        self, user_id: UUID, task_id: UUID, data: WatcherRequest
    ) -> list[User]:
        task = await self.get_task(user_id, task_id)
        project = await self.repository.get_project(task.project_id)
        if project is None:
            raise NotFoundError("Task not found")
        target_id = data.user_id or user_id
        if target_id != user_id:
            self._require_watcher_manager(user_id, task, project.owner_id)
        await self._require_organization_user(project.organization_id, target_id)
        existing = await self.repository.get_task_watcher(task.id, target_id)
        await self.repository.add_project_member(task.project_id, target_id)
        await self.repository.add_task_watcher(task.id, target_id)
        if existing is None:
            await self._record_history(
                task, user_id, "watcher_added", "watcher", None, await self._display_name(target_id)
            )
        await self.session.commit()
        return await self.repository.list_task_watchers(task.id)

    async def remove_task_watcher(
        self, user_id: UUID, task_id: UUID, watcher_id: UUID
    ) -> list[User]:
        task = await self.get_task(user_id, task_id)
        project = await self.repository.get_project(task.project_id)
        if project is None:
            raise NotFoundError("Task not found")
        if watcher_id != user_id:
            self._require_watcher_manager(user_id, task, project.owner_id)
        if await self.repository.get_task_watcher(task.id, watcher_id) is None:
            raise NotFoundError("Task watcher not found")
        old_value = await self._display_name(watcher_id)
        await self.repository.remove_task_watcher(task.id, watcher_id)
        await self._record_history(task, user_id, "watcher_removed", "watcher", old_value, None)
        await self.session.commit()
        return await self.repository.list_task_watchers(task.id)

    async def list_notifications(self, user_id: UUID) -> list[NotificationResponse]:
        return [
            NotificationResponse.model_validate(item)
            for item in await self.repository.list_notifications(user_id)
        ]

    async def unread_notification_count(self, user_id: UUID) -> UnreadCountResponse:
        return UnreadCountResponse(count=await self.repository.count_unread_notifications(user_id))

    async def open_notification(self, user_id: UUID, notification_id: UUID) -> NotificationResponse:
        notification = await self.repository.get_notification(notification_id)
        if notification is None or notification.recipient_id != user_id:
            raise NotFoundError("Notification not found")
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            await self.session.commit()
        return NotificationResponse.model_validate(notification)

    async def get_board(self, user_id: UUID, project_id: UUID, limit: int) -> BoardResponse:
        await self.get_project(user_id, project_id)
        columns = []
        for project_status in await self.repository.list_statuses(project_id):
            tasks = await self.repository.list_tasks_for_status(
                project_id, project_status.id, limit
            )
            next_cursor = None
            if len(tasks) > limit:
                tasks = tasks[:limit]
                next_cursor = encode_cursor(tasks[-1].updated_at, tasks[-1].id)
            columns.append(
                BoardColumnResponse(
                    status=StatusResponse.model_validate(project_status),
                    tasks=[await self._task_response(task) for task in tasks],
                    next_cursor=next_cursor,
                )
            )
        return BoardResponse(project_id=project_id, columns=columns)

    async def get_column_tasks(
        self, user_id: UUID, project_id: UUID, status_id: UUID, limit: int, cursor: str | None
    ) -> TaskPageResponse:
        await self.get_project(user_id, project_id)
        project_status = await self._get_project_status(project_id, status_id)
        if not project_status.is_active:
            raise NotFoundError("Status not found")
        page = await self.repository.list_tasks_for_status(
            project_id, status_id, limit, self._decode_cursor(cursor) if cursor else None
        )
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = encode_cursor(page[-1].updated_at, page[-1].id)
        return TaskPageResponse(
            tasks=[await self._task_response(task) for task in page], next_cursor=next_cursor
        )

    async def get_task_history(
        self, user_id: UUID, task_id: UUID, limit: int, cursor: str | None
    ) -> TaskHistoryPageResponse:
        await self.get_task(user_id, task_id)
        page = await self.repository.list_task_history(
            task_id, limit, self._decode_cursor(cursor) if cursor else None
        )
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = encode_cursor(page[-1].created_at, page[-1].id)
        return TaskHistoryPageResponse(
            entries=[
                TaskHistoryResponse(
                    id=item.id,
                    task_id=item.task_id,
                    changed_by=item.changed_by,
                    actor=ProfileResponse.model_validate(item.actor.profile),
                    from_status_id=item.from_status_id,
                    to_status_id=item.to_status_id,
                    event_type=item.event_type,
                    field_name=item.field_name,
                    old_value=item.old_value,
                    new_value=item.new_value,
                    created_at=item.created_at,
                )
                for item in page
            ],
            next_cursor=next_cursor,
        )

    async def _get_project_status(self, project_id: UUID, status_id: UUID) -> ProjectStatus:
        project_status = await self.repository.get_status(status_id)
        if project_status is None or project_status.project_id != project_id:
            raise NotFoundError("Status not found")
        return project_status

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
        try:
            return decode_cursor(cursor)
        except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
            raise InvalidWorkflowError("Invalid cursor") from exc

    async def _task_response(self, task: Task) -> TaskResponse:
        watchers = await self.repository.list_task_watchers(task.id)
        return TaskResponse(
            id=task.id,
            project_id=task.project_id,
            status_id=task.status_id,
            title=task.title,
            description=task.description,
            created_by=task.created_by,
            reporter_id=task.reporter_id,
            assignee_id=task.assignee_id,
            watchers=[UserSummary.model_validate(user) for user in watchers],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    async def _require_organization_user(self, organization_id: UUID, user_id: UUID) -> User:
        user = await self.repository.get_user(user_id)
        if (
            user is None
            or not user.is_active
            or not await self.repository.has_organization_access(organization_id, user_id)
        ):
            raise InvalidWorkflowError("User must belong to the task organization")
        return user

    async def _record_history(
        self,
        task: Task,
        actor_id: UUID,
        event_type: str,
        field_name: str,
        old_value: str | None,
        new_value: str | None,
    ) -> None:
        self.session.add(
            TaskHistory(
                task_id=task.id,
                changed_by=actor_id,
                event_type=event_type,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
        )

    async def _display_name(self, user_id: UUID | None) -> str | None:
        if user_id is None:
            return None
        user = await self.repository.get_user(user_id)
        if user is None or user.profile is None:
            return "Unknown user"
        return f"{user.profile.first_name} {user.profile.last_name}"

    async def _queue_notifications(
        self,
        task: Task,
        actor_id: UUID,
        events: list[tuple[str, str, dict[str, str]]],
    ) -> None:
        if not events:
            return
        watcher_ids = await self.repository.list_task_watcher_ids(task.id)
        for event_type, message, event_data in events:
            payload = json.dumps(event_data, separators=(",", ":"))
            for watcher_id in watcher_ids:
                if watcher_id != actor_id:
                    self.repository.add_notification(
                        recipient_id=watcher_id,
                        task_id=task.id,
                        event_type=event_type,
                        message=message,
                        event_data=payload,
                    )

    @staticmethod
    def _require_assignee_permission(
        user_id: UUID, task: Task, project_owner_id: UUID, new_assignee_id: UUID | None
    ) -> None:
        if task.assignee_id is None and new_assignee_id == user_id:
            return
        if user_id not in {project_owner_id, task.assignee_id}:
            raise PermissionDeniedError(
                "Only the project owner or current assignee can change assignee"
            )

    @staticmethod
    def _require_reporter_permission(user_id: UUID, task: Task, project_owner_id: UUID) -> None:
        if user_id not in {project_owner_id, task.reporter_id}:
            raise PermissionDeniedError("Only the project owner or reporter can change reporter")

    @staticmethod
    def _require_watcher_manager(user_id: UUID, task: Task, project_owner_id: UUID) -> None:
        if user_id not in {project_owner_id, task.assignee_id}:
            raise PermissionDeniedError("Only the project owner or assignee can manage watchers")

    async def _find_user(self, email: str) -> User:
        user = await self.repository.get_user_by_email(normalized_email(str(email)))
        if user is None or not user.is_active:
            raise NotFoundError("User not found")
        return user

    async def _get_deleted_organization(self, organization_id: UUID) -> Organization:
        organization = await self.repository.get_organization(organization_id)
        if organization is None or organization.deleted_at is None:
            raise NotFoundError("Organization not found")
        return organization

    async def _get_deleted_project(self, project_id: UUID) -> Project:
        project = await self.repository.get_project(project_id)
        if project is None or project.deleted_at is None:
            raise NotFoundError("Project not found")
        return project

    @staticmethod
    def _require_owner(user_id: UUID, owner_id: UUID) -> None:
        if user_id != owner_id:
            raise PermissionDeniedError("Only the owner can perform this operation")

    @staticmethod
    def _require_confirmation(data: ConfirmRequest) -> None:
        if not data.confirm:
            raise InvalidWorkflowError("Explicit confirmation is required")

    async def _renumber(self, statuses: list[ProjectStatus]) -> None:
        for index, project_status in enumerate(statuses):
            project_status.position = -(index + 1)
        await self.session.flush()
        for index, project_status in enumerate(statuses):
            project_status.position = index
        await self.session.flush()
