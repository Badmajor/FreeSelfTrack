from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.administration import AdministrationRepository
from app.repositories.domain import DomainRepository
from app.services.errors import PermissionDeniedError


class AdministrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = AdministrationRepository(session)
        self.domain = DomainRepository(session)

    async def level(self, user_id: UUID) -> int:
        user = await self.domain.get_user(user_id)
        if user is None or not user.is_active:
            return -1
        if user.is_system_admin:
            return 3
        if await self.repository.active_manager(user_id):
            return 2
        if await self.repository.has_project_manager_role(user_id):
            return 1
        return 0

    async def can_manage(
        self, user_id: UUID, organization_id: UUID | None = None, project_id: UUID | None = None
    ) -> bool:
        user = await self.domain.get_user(user_id)
        if user is None or not user.is_active:
            return False
        if user.is_system_admin:
            return True
        if organization_id is not None and await self.repository.active_manager(
            user_id, organization_id
        ):
            return True
        return project_id is not None and await self.repository.active_manager(
            user_id, project_id=project_id
        )

    async def require_manager(
        self, user_id: UUID, organization_id: UUID | None = None, project_id: UUID | None = None
    ) -> None:
        if not await self.can_manage(user_id, organization_id, project_id):
            raise PermissionDeniedError("Administrative permission required")

    async def require_lower_level(self, actor_id: UUID, target_id: UUID) -> None:
        actor_level = await self.level(actor_id)
        if actor_level == 3 and actor_id == target_id:
            return
        if actor_level <= await self.level(target_id):
            raise PermissionDeniedError("Target must have a lower global role")
