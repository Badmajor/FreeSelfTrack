from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, Project, ProjectStatus, Task
from app.repositories.domain import DomainRepository
from app.schemas.domain import (
    OrganizationCreate,
    ProjectCreate,
    ProjectUpdate,
    StatusCreate,
    StatusReorder,
    StatusUpdate,
    TaskCreate,
    TaskUpdate,
)
from app.services.errors import InvalidWorkflowError, NotFoundError


class DomainService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DomainRepository(session)

    async def create_organization(self, user_id: UUID, data: OrganizationCreate) -> Organization:
        organization = Organization(name=data.name)
        self.session.add(organization)
        await self.session.flush()
        await self.repository.add_organization_member(organization.id, user_id)
        await self.session.commit()
        return organization

    async def list_organizations(self, user_id: UUID) -> list[Organization]:
        return await self.repository.list_organizations_for_user(user_id)

    async def get_organization(self, user_id: UUID, organization_id: UUID) -> Organization:
        organization = await self.repository.get_organization(organization_id)
        if organization is None or not await self.repository.has_organization_access(
            organization_id, user_id
        ):
            raise NotFoundError("Organization not found")
        return organization

    async def create_project(self, user_id: UUID, data: ProjectCreate) -> Project:
        if not await self.repository.has_organization_access(data.organization_id, user_id):
            raise NotFoundError("Organization not found")
        project = Project(organization_id=data.organization_id, name=data.name)
        self.session.add(project)
        await self.session.flush()
        await self.repository.add_project_member(project.id, user_id)
        await self.session.commit()
        return project

    async def get_project(self, user_id: UUID, project_id: UUID) -> Project:
        project = await self.repository.get_project(project_id)
        if project is None or not await self.repository.has_project_access(project_id, user_id):
            raise NotFoundError("Project not found")
        return project

    async def update_project(self, user_id: UUID, project_id: UUID, data: ProjectUpdate) -> Project:
        project = await self.get_project(user_id, project_id)
        if data.name is not None:
            project.name = data.name
        await self.session.commit()
        return project

    async def create_status(
        self, user_id: UUID, project_id: UUID, data: StatusCreate
    ) -> ProjectStatus:
        await self.get_project(user_id, project_id)
        statuses = await self.repository.list_statuses(project_id)
        position = len(statuses) if data.position is None else min(data.position, len(statuses))
        status = ProjectStatus(
            project_id=project_id, name=data.name, position=position, is_active=data.is_active
        )
        self.session.add(status)
        statuses.insert(position, status)
        await self._renumber(statuses)
        await self.session.commit()
        return status

    async def list_statuses(self, user_id: UUID, project_id: UUID) -> list[ProjectStatus]:
        await self.get_project(user_id, project_id)
        return await self.repository.list_statuses(project_id)

    async def update_status(
        self, user_id: UUID, project_id: UUID, status_id: UUID, data: StatusUpdate
    ) -> ProjectStatus:
        await self.get_project(user_id, project_id)
        status = await self.repository.get_status(status_id)
        if status is None or status.project_id != project_id:
            raise NotFoundError("Status not found")
        if data.name is not None:
            status.name = data.name
        if data.is_active is not None:
            status.is_active = data.is_active
        if data.position is not None and data.position != status.position:
            statuses = await self.repository.list_statuses(project_id)
            statuses.remove(status)
            statuses.insert(min(data.position, len(statuses)), status)
            await self._renumber(statuses)
        await self.session.commit()
        return status

    async def reorder_statuses(
        self, user_id: UUID, project_id: UUID, data: StatusReorder
    ) -> list[ProjectStatus]:
        await self.get_project(user_id, project_id)
        statuses = await self.repository.list_statuses(project_id)
        current_ids = {status.id for status in statuses}
        requested_ids = data.status_ids
        if len(requested_ids) != len(set(requested_ids)) or set(requested_ids) != current_ids:
            raise InvalidWorkflowError("status_ids must contain every project status exactly once")
        by_id = {status.id: status for status in statuses}
        ordered = [by_id[status_id] for status_id in requested_ids]
        await self._renumber(ordered)
        await self.session.commit()
        return ordered

    async def create_task(self, user_id: UUID, project_id: UUID, data: TaskCreate) -> Task:
        await self.get_project(user_id, project_id)
        status = await self.repository.get_status(data.status_id)
        if status is None or status.project_id != project_id:
            raise InvalidWorkflowError("Task status must belong to the task project")
        task = Task(
            project_id=project_id,
            status_id=status.id,
            title=data.title,
            description=data.description,
            created_by=user_id,
        )
        self.session.add(task)
        await self.session.commit()
        return task

    async def get_task(self, user_id: UUID, task_id: UUID) -> Task:
        task = await self.repository.get_task(task_id)
        if task is None or not await self.repository.has_project_access(task.project_id, user_id):
            raise NotFoundError("Task not found")
        return task

    async def update_task(self, user_id: UUID, task_id: UUID, data: TaskUpdate) -> Task:
        task = await self.get_task(user_id, task_id)
        if data.title is not None:
            task.title = data.title
        if "description" in data.model_fields_set:
            task.description = data.description
        if data.status_id is not None:
            status = await self.repository.get_status(data.status_id)
            if status is None or status.project_id != task.project_id:
                raise InvalidWorkflowError("Task status must belong to the task project")
            task.status_id = status.id
        await self.session.commit()
        return task

    async def _renumber(self, statuses: list[ProjectStatus]) -> None:
        # A temporary negative range avoids collisions with the unique position constraint.
        for index, status in enumerate(statuses):
            status.position = -(index + 1)
        await self.session.flush()
        for index, status in enumerate(statuses):
            status.position = index
        await self.session.flush()
