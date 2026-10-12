from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import translate_errors
from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.schemas.audit_views import AdministrativeAuditPage, AuditQuery
from app.services.audit_views import AuditViewService

router = APIRouter(tags=["administrative audit"])


@router.get("/users/{entity_id}/audit", response_model=AdministrativeAuditPage)
async def user_audit(
    entity_id: UUID,
    query: Annotated[AuditQuery, Query()],
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(AuditViewService(session).page)(
        actor_id, "user", entity_id, query.cursor
    )


@router.get("/organizations/{entity_id}/audit", response_model=AdministrativeAuditPage)
async def organization_audit(
    entity_id: UUID,
    query: Annotated[AuditQuery, Query()],
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(AuditViewService(session).page)(
        actor_id, "organization", entity_id, query.cursor
    )


@router.get("/projects/{entity_id}/audit", response_model=AdministrativeAuditPage)
async def project_audit(
    entity_id: UUID,
    query: Annotated[AuditQuery, Query()],
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(AuditViewService(session).page)(
        actor_id, "project", entity_id, query.cursor
    )


@router.get("/tasks/{entity_id}/audit", response_model=AdministrativeAuditPage)
async def task_audit(
    entity_id: UUID,
    query: Annotated[AuditQuery, Query()],
    actor_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(AuditViewService(session).page)(
        actor_id, "task", entity_id, query.cursor
    )
