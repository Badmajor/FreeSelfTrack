import binascii
import json
import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cursor import decode_cursor, encode_cursor
from app.models import (
    Organization,
    Project,
    ProjectStatus,
    ProjectTaskSequence,
    Task,
    TaskHistory,
    TaskLink,
    User,
)
from app.repositories.domain import DomainRepository
from app.schemas.domain import (
    BoardColumnResponse,
    BoardResponse,
    ConfirmRequest,
    MembershipRequest,
    NotificationResponse,
    OrganizationCreate,
    ParticipantSummary,
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
    TaskLinkCreate,
    TaskLinkResponse,
    TaskLinkTaskSummary,
    TaskPageResponse,
    TaskResponse,
    TaskSearchResponse,
    TaskUpdate,
    UnreadCountResponse,
    WatcherRequest,
)
from app.services.errors import (
    ConflictError,
    InvalidWorkflowError,
    NotFoundError,
    PermissionDeniedError,
)

DEFAULT_STATUSES = ("Backlog", "In Progress", "Done")


def project_slug_prefix(name: str) -> str:
    words = re.findall(r"[^\W_]+", name, flags=re.UNICODE)
    if len(words) > 1:
        prefix = "".join(word[0] for word in words)
    elif words:
        prefix = words[0][:3]
    else:
        prefix = "TASK"
    return prefix.upper()[:40] or "TASK"


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
        self.session.add(ProjectTaskSequence(project_id=project.id, next_number=1))
        await self.repository.add_project_member(project.id, user_id)
        for position, name in enumerate(DEFAULT_STATUSES):
            self.session.add(
                ProjectStatus(
                    project_id=project.id,
                    name=name,
                    position=position,
                    is_completed=name == "Done",
                )
            )
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

    async def get_project_for_read(self, user_id: UUID, project_id: UUID) -> Project:
        project = await self.repository.get_project(project_id)
        if (
            project is None
            or project.deleted_at is not None
            or not await self.repository.has_organization_access(project.organization_id, user_id)
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
            project_id=project_id,
            name=data.name,
            position=position,
            is_active=data.is_active,
            is_completed=data.is_completed,
        )
        self.session.add(project_status)
        statuses.insert(position, project_status)
        await self._renumber(statuses)
        await self.session.commit()
        return project_status

    async def list_statuses(self, user_id: UUID, project_id: UUID) -> list[ProjectStatus]:
        await self.get_project_for_read(user_id, project_id)
        return await self.repository.list_statuses(project_id)

    async def list_archived_statuses(self, user_id: UUID, project_id: UUID) -> list[ProjectStatus]:
        await self.get_project_for_read(user_id, project_id)
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
        if data.is_completed is not None:
            if project_status.is_completed and not data.is_completed:
                statuses = await self.repository.list_statuses(project_id)
                if sum(status.is_completed for status in statuses) <= 1:
                    raise ConflictError("At least one active completing status must remain")
            project_status.is_completed = data.is_completed
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
        if project_status.is_completed:
            statuses = await self.repository.list_statuses(project_id)
            if sum(status.is_completed for status in statuses) <= 1:
                raise ConflictError("At least one active completing status must remain")
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
        sequence = await self.repository.get_project_task_sequence(project_id)
        if sequence is None:
            raise ConflictError("Project task sequence is not initialized")
        sequence_number = sequence.next_number
        sequence.next_number += 1
        slug = f"{project_slug_prefix(project.name)}-{sequence_number}"
        await self._require_organization_user(project.organization_id, reporter_id)
        await self.repository.add_project_member(project_id, reporter_id)
        if data.assignee_id is not None:
            await self._require_organization_user(project.organization_id, data.assignee_id)
            await self.repository.add_project_member(project_id, data.assignee_id)
        if (
            data.story_points is not None or data.due_date is not None or data.priority is not None
        ) and user_id not in {
            project.owner_id,
            reporter_id,
            data.assignee_id,
        }:
            raise PermissionDeniedError(
                "Only the project owner, reporter, or assignee can set planning fields"
            )
        task = Task(
            project_id=project_id,
            status_id=project_status.id,
            title=data.title,
            description=data.description,
            slug=slug,
            sequence_number=sequence_number,
            created_by=user_id,
            reporter_id=reporter_id,
            assignee_id=data.assignee_id,
            story_points=data.story_points,
            due_date=data.due_date,
            priority=data.priority,
        )
        self.session.add(task)
        await self.session.flush()
        if data.priority is not None:
            await self._record_history(
                task,
                user_id,
                "priority_changed",
                "priority",
                None,
                data.priority,
            )
        if data.story_points is not None:
            await self._record_history(
                task,
                user_id,
                "story_points_changed",
                "story_points",
                None,
                str(data.story_points),
            )
        if data.due_date is not None:
            await self._record_history(
                task,
                user_id,
                "due_date_changed",
                "due_date",
                None,
                data.due_date.isoformat(),
            )
            await self._queue_deadline_change_notifications(task, user_id)
        await self.session.commit()
        return task

    async def create_task_response(
        self, user_id: UUID, project_id: UUID, data: TaskCreate
    ) -> TaskResponse:
        task = await self.create_task(user_id, project_id, data)
        return await self._task_response(task)

    async def get_task(self, user_id: UUID, task_id: UUID) -> Task:
        task = await self.repository.get_task(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        project = await self.get_project_for_read(user_id, task.project_id)
        if project.deleted_at is not None:
            raise NotFoundError("Task not found")
        return task

    async def get_task_response(self, user_id: UUID, task_id: UUID) -> TaskResponse:
        return await self._task_response(await self.get_task(user_id, task_id))

    async def update_task(self, user_id: UUID, task_id: UUID, data: TaskUpdate) -> Task:
        task = await self.get_task(user_id, task_id)
        if not await self.repository.has_project_access(task.project_id, user_id):
            raise PermissionDeniedError("Project membership is required to update tasks")
        project = await self.repository.get_project(task.project_id)
        if project is None:
            raise NotFoundError("Task not found")
        can_manage_planning = user_id in {project.owner_id, task.reporter_id, task.assignee_id}
        events: list[tuple[str, str, dict[str, str]]] = []
        if data.title is not None and data.title != task.title:
            old_title = task.title
            task.title = data.title
            await self._record_history(
                task, user_id, "title_changed", "title", old_title, data.title
            )
            events.append(("title_changed", "Task title changed", {"title": data.title}))
        if "description" in data.model_fields_set and data.description != task.description:
            old_description = task.description
            task.description = data.description
            await self._record_history(
                task,
                user_id,
                "description_changed",
                "description",
                old_description,
                data.description,
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
            await self.repository.add_project_member(task.project_id, data.reporter_id)
            if data.reporter_id != task.reporter_id:
                old_reporter = await self._display_name(task.reporter_id)
                new_reporter = await self._display_name(data.reporter_id)
                task.reporter_id = data.reporter_id
                await self._record_history(
                    task, user_id, "reporter_changed", "reporter", old_reporter, new_reporter
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
                await self.repository.add_project_member(task.project_id, data.assignee_id)
            if data.assignee_id != task.assignee_id:
                old_assignee = (
                    await self._display_name(task.assignee_id) if task.assignee_id else None
                )
                new_assignee = (
                    await self._display_name(data.assignee_id) if data.assignee_id else None
                )
                task.assignee_id = data.assignee_id
                await self._record_history(
                    task, user_id, "assignee_changed", "assignee", old_assignee, new_assignee
                )
                events.append(
                    (
                        "assignee_changed",
                        "Task assignee changed",
                        {"assignee_id": str(data.assignee_id) if data.assignee_id else ""},
                    )
                )
        if "story_points" in data.model_fields_set and data.story_points != task.story_points:
            if not can_manage_planning:
                raise PermissionDeniedError(
                    "Only the project owner, reporter, or assignee can change story points"
                )
            old_points = str(task.story_points) if task.story_points is not None else None
            new_points = str(data.story_points) if data.story_points is not None else None
            task.story_points = data.story_points
            await self._record_history(
                task, user_id, "story_points_changed", "story_points", old_points, new_points
            )
        if "priority" in data.model_fields_set and data.priority != task.priority:
            if not can_manage_planning:
                raise PermissionDeniedError(
                    "Only the project owner, reporter, or assignee can change priority"
                )
            old_priority = task.priority
            task.priority = data.priority
            await self._record_history(
                task,
                user_id,
                "priority_changed",
                "priority",
                old_priority,
                data.priority,
            )
        deadline_changed = "due_date" in data.model_fields_set and data.due_date != task.due_date
        if deadline_changed:
            if not can_manage_planning:
                raise PermissionDeniedError(
                    "Only the project owner, reporter, or assignee can change deadline"
                )
            old_deadline = task.due_date.isoformat() if task.due_date is not None else None
            new_deadline = data.due_date.isoformat() if data.due_date is not None else None
            task.due_date = data.due_date
            await self._record_history(
                task, user_id, "due_date_changed", "due_date", old_deadline, new_deadline
            )
        await self._queue_notifications(task, user_id, events)
        if deadline_changed:
            await self._queue_deadline_change_notifications(task, user_id)
        await self.session.commit()
        return task

    async def update_task_response(
        self, user_id: UUID, task_id: UUID, data: TaskUpdate
    ) -> TaskResponse:
        return await self._task_response(await self.update_task(user_id, task_id, data))

    async def search_organization_tasks(
        self, user_id: UUID, organization_id: UUID, slug: str, limit: int
    ) -> TaskSearchResponse:
        await self.get_organization(user_id, organization_id)
        normalized = slug.strip()
        if not normalized:
            raise InvalidWorkflowError("Task slug is required")
        rows = await self.repository.search_organization_tasks(organization_id, normalized, limit)
        return TaskSearchResponse(
            items=[self._task_link_summary(task, project, status) for task, project, status in rows]
        )

    async def list_task_links(self, user_id: UUID, task_id: UUID) -> list[TaskLinkResponse]:
        task = await self.get_task(user_id, task_id)
        responses: list[TaskLinkResponse] = []
        for link in await self.repository.list_task_links(task_id):
            other_id = link.task_b_id if task.id == link.task_a_id else link.task_a_id
            other = await self.repository.get_task(other_id)
            project = (
                await self.repository.get_project(other.project_id) if other is not None else None
            )
            if project is None or project.deleted_at is not None:
                continue
            responses.append(await self._task_link_response(task, link))
        return responses

    async def create_task_link(
        self, user_id: UUID, task_id: UUID, data: TaskLinkCreate
    ) -> tuple[TaskLinkResponse, bool]:
        source = await self.get_task(user_id, task_id)
        target = await self.repository.get_task(data.target_task_id)
        if target is None:
            raise NotFoundError("Task not found")
        source_project = await self.repository.get_project(source.project_id)
        target_project = await self.repository.get_project(target.project_id)
        if (
            source_project is None
            or target_project is None
            or target_project.deleted_at is not None
            or source_project.organization_id != target_project.organization_id
        ):
            raise NotFoundError("Task not found")
        if source.id == target.id:
            raise InvalidWorkflowError("A task cannot link to itself")
        await self.get_organization(user_id, source_project.organization_id)
        if not (
            await self.repository.has_project_access(source.project_id, user_id)
            or await self.repository.has_project_access(target.project_id, user_id)
        ):
            raise PermissionDeniedError("Project membership is required to manage links")
        task_a_id, task_b_id = sorted((source.id, target.id), key=lambda value: value.int)
        relation_type = "related" if data.relation_type == "related" else "blocks"
        blocking_task_id = None
        if data.relation_type == "blocks":
            blocking_task_id = source.id
        elif data.relation_type == "depends_on":
            blocking_task_id = target.id
        # Lock in canonical order so concurrent requests for the same pair serialize.
        await self.repository.lock_task_pair(task_a_id, task_b_id)
        existing = await self.repository.get_task_link_pair(task_a_id, task_b_id)
        if existing is not None:
            if (
                existing.relation_type == relation_type
                and existing.blocking_task_id == blocking_task_id
            ):
                return await self._task_link_response(source, existing), False
            raise ConflictError("Tasks are already linked with another relation")
        link = TaskLink(
            task_a_id=task_a_id,
            task_b_id=task_b_id,
            relation_type=relation_type,
            blocking_task_id=blocking_task_id,
            created_by=user_id,
        )
        self.session.add(link)
        try:
            await self.session.flush()
        except IntegrityError as error:
            await self.session.rollback()
            existing = await self.repository.get_task_link_pair(task_a_id, task_b_id)
            if existing is None:
                raise
            if (
                existing.relation_type == relation_type
                and existing.blocking_task_id == blocking_task_id
            ):
                source_after_race = await self.get_task(user_id, task_id)
                return await self._task_link_response(source_after_race, existing), False
            raise ConflictError("Tasks are already linked with another relation") from error
        await self._record_link_change(source, target, user_id, link, "task_link_added")
        await self._record_link_change(target, source, user_id, link, "task_link_added")
        await self._queue_link_notifications(source, target, user_id, link, "task_link_added")
        await self.session.commit()
        return await self._task_link_response(source, link), True

    async def delete_task_link(self, user_id: UUID, task_id: UUID, link_id: UUID) -> None:
        source = await self.get_task(user_id, task_id)
        link = await self.repository.get_task_link(link_id)
        if link is None or source.id not in {link.task_a_id, link.task_b_id}:
            raise NotFoundError("Task link not found")
        other_id = link.task_b_id if source.id == link.task_a_id else link.task_a_id
        target = await self.repository.get_task(other_id)
        if target is None:
            raise NotFoundError("Task link not found")
        if not (
            await self.repository.has_project_access(source.project_id, user_id)
            or await self.repository.has_project_access(target.project_id, user_id)
        ):
            raise PermissionDeniedError("Project membership is required to manage links")
        await self._record_link_change(source, target, user_id, link, "task_link_removed")
        await self._record_link_change(target, source, user_id, link, "task_link_removed")
        await self._queue_link_notifications(source, target, user_id, link, "task_link_removed")
        await self.session.delete(link)
        await self.session.commit()

    async def list_task_watchers(self, user_id: UUID, task_id: UUID) -> list[ParticipantSummary]:
        await self.get_task(user_id, task_id)
        return [
            self._participant_summary(user)
            for user in await self.repository.list_task_watchers(task_id)
        ]

    async def add_task_watcher(
        self, user_id: UUID, task_id: UUID, data: WatcherRequest
    ) -> list[ParticipantSummary]:
        task = await self.get_task(user_id, task_id)
        if not await self.repository.has_project_access(task.project_id, user_id):
            raise PermissionDeniedError("Project membership is required to manage watchers")
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
        return [
            self._participant_summary(user)
            for user in await self.repository.list_task_watchers(task.id)
        ]

    async def remove_task_watcher(
        self, user_id: UUID, task_id: UUID, watcher_id: UUID
    ) -> list[ParticipantSummary]:
        task = await self.get_task(user_id, task_id)
        if not await self.repository.has_project_access(task.project_id, user_id):
            raise PermissionDeniedError("Project membership is required to manage watchers")
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
        return [
            self._participant_summary(user)
            for user in await self.repository.list_task_watchers(task.id)
        ]

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
        await self.get_project_for_read(user_id, project_id)
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
        await self.get_project_for_read(user_id, project_id)
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
        reporter = await self.repository.get_user(task.reporter_id)
        assignee = (
            await self.repository.get_user(task.assignee_id)
            if task.assignee_id is not None
            else None
        )
        if reporter is None or reporter.profile is None:
            raise NotFoundError("Task reporter not found")
        return TaskResponse(
            id=task.id,
            project_id=task.project_id,
            status_id=task.status_id,
            slug=task.slug,
            title=task.title,
            description=task.description,
            created_by=task.created_by,
            reporter_id=task.reporter_id,
            assignee_id=task.assignee_id,
            story_points=task.story_points,
            due_date=task.due_date,
            priority=task.priority,
            reporter=self._participant_summary(reporter),
            assignee=(
                self._participant_summary(assignee)
                if assignee is not None and assignee.profile is not None
                else None
            ),
            watchers=[self._participant_summary(user) for user in watchers],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    def _task_link_summary(
        task: Task, project: Project, status: ProjectStatus
    ) -> TaskLinkTaskSummary:
        return TaskLinkTaskSummary(
            id=task.id,
            slug=task.slug,
            title=task.title,
            project_id=project.id,
            project_name=project.name,
            status_id=status.id,
            status_name=status.name,
        )

    async def _task_link_response(self, source: Task, link: TaskLink) -> TaskLinkResponse:
        other_id = link.task_b_id if source.id == link.task_a_id else link.task_a_id
        other = await self.repository.get_task(other_id)
        if other is None:
            raise NotFoundError("Linked task not found")
        project = await self.repository.get_project(other.project_id)
        status = await self.repository.get_status(other.status_id)
        creator = await self.repository.get_user(link.created_by)
        if project is None or status is None or creator is None or creator.profile is None:
            raise NotFoundError("Linked task not found")
        if link.relation_type == "related":
            relation_type: Literal["blocks", "depends_on", "related"] = "related"
        elif link.blocking_task_id == source.id:
            relation_type = "blocks"
        else:
            relation_type = "depends_on"
        return TaskLinkResponse(
            id=link.id,
            relation_type=relation_type,
            task=self._task_link_summary(other, project, status),
            created_by=self._participant_summary(creator),
            created_at=link.created_at,
        )

    async def _record_link_change(
        self, task: Task, other: Task, actor_id: UUID, link: TaskLink, event_type: str
    ) -> None:
        relation = (
            "related"
            if link.relation_type == "related"
            else "blocks"
            if link.blocking_task_id == task.id
            else "depends_on"
        )
        await self._record_history(
            task,
            actor_id,
            event_type,
            "links",
            None if event_type == "task_link_added" else f"{relation}: {other.slug} {other.title}",
            f"{relation}: {other.slug} {other.title}" if event_type == "task_link_added" else None,
        )

    async def _queue_link_notifications(
        self, source: Task, target: Task, actor_id: UUID, link: TaskLink, event_type: str
    ) -> None:
        recipients: set[UUID] = set()
        for task in (source, target):
            recipients.add(task.reporter_id)
            if task.assignee_id is not None:
                recipients.add(task.assignee_id)
            recipients.update(await self.repository.list_task_watcher_ids(task.id))
        payload = json.dumps(
            {
                "project_id": str(source.project_id),
                "linked_task_id": str(target.id),
                "link_id": str(link.id),
                "tab": "links",
            },
            separators=(",", ":"),
        )
        action = "linked" if event_type == "task_link_added" else "unlinked"
        for recipient_id in recipients - {actor_id}:
            self.repository.add_notification(
                recipient_id=recipient_id,
                task_id=source.id,
                event_type=event_type,
                message=f"Task {source.slug} {action} with {target.slug}",
                event_data=payload,
            )

    @staticmethod
    def _participant_summary(user: User) -> ParticipantSummary:
        if user.profile is None:
            raise NotFoundError("User profile not found")
        return ParticipantSummary(
            id=user.id,
            first_name=user.profile.first_name,
            last_name=user.profile.last_name,
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

    async def _queue_deadline_change_notifications(self, task: Task, actor_id: UUID) -> None:
        project = await self.repository.get_project(task.project_id)
        if project is None:
            return
        project_members = await self.repository.list_project_members(task.project_id)
        organization_members = await self.repository.list_organization_members(
            project.organization_id
        )
        organization_ids = {user.id for user in organization_members if user.is_active}
        allowed_ids = {
            user.id for user in project_members if user.is_active and user.id in organization_ids
        }
        role_ids = {task.reporter_id}
        if task.assignee_id is not None:
            role_ids.add(task.assignee_id)
        recipients = (
            role_ids | set(await self.repository.list_task_watcher_ids(task.id))
        ) & allowed_ids
        due_date = task.due_date.isoformat() if task.due_date is not None else None
        if due_date is None:
            message = f"Deadline removed from {task.slug}"
        else:
            message = f"Deadline for {task.slug} changed to {due_date}"
        payload = json.dumps(
            {"project_id": str(task.project_id), "due_date": due_date}, separators=(",", ":")
        )
        for recipient_id in recipients - {actor_id}:
            self.repository.add_notification(
                recipient_id=recipient_id,
                task_id=task.id,
                event_type="due_date_changed",
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
