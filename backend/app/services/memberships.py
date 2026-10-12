"""Administrative membership operations; one lifecycle lock and transaction per mutation."""

import base64
import binascii
import json
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, Project, User
from app.repositories.administration import AdministrationRepository
from app.repositories.domain import DomainRepository
from app.repositories.memberships import Membership, MembershipRepository, Scope
from app.repositories.sessions import SessionRepository
from app.schemas.administrative_audit import AdministrativeAuditWrite, AuditChange
from app.schemas.domain import MembershipPage, MembershipResponse, MemberUser
from app.services.administration import AdministrationService
from app.services.administrative_audit import AdministrativeAuditService
from app.services.audit import record_event
from app.services.errors import AdministrativeError, PermissionDeniedError
from app.services.sessions import SessionService, invalid_session


class MembershipService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.domain = DomainRepository(session)
        self.roles = AdministrationService(session)
        self.repository = MembershipRepository(session)
        self.audit_writer = AdministrativeAuditService(session)

    async def lock(self, actor_id: UUID) -> None:
        await AdministrationRepository(self.session).lock_lifecycle()
        actor = await SessionRepository(self.session).lock_user(actor_id)
        if actor is None or not actor.is_active:
            raise invalid_session()
        await SessionService(self.session).recheck_request_session(actor_id)

    async def resource(
        self, actor_id: UUID, scope: Scope, scope_id: UUID, *, mutate: bool = False
    ) -> Organization | Project:
        resource = (
            await self.domain.get_organization(scope_id)
            if scope == "organization"
            else await self.domain.get_project(scope_id)
        )
        if resource is None:
            raise AdministrativeError(404, "not_found", "Resource not found")
        org_id = resource.organization_id if isinstance(resource, Project) else resource.id
        organization = await self.domain.get_organization(org_id)
        assert organization is not None
        from app.repositories.task_access import TaskAccessRepository

        can_read = (
            await self.domain.has_organization_access(scope_id, actor_id)
            if scope == "organization"
            else await TaskAccessRepository(self.session).can_read_project(actor_id, scope_id)
        )
        if not can_read:
            raise AdministrativeError(404, "not_found", "Resource not found")
        if mutate:
            if not await self.roles.can_manage(
                actor_id, org_id, resource.id if isinstance(resource, Project) else None
            ):
                raise AdministrativeError(
                    403, "permission_denied", "Administrative permission required"
                )
            if organization.archived_at is not None:
                code = "object_archived" if scope == "organization" else "parent_archived"
                raise AdministrativeError(409, code, "Restore the organization first")
            if resource.archived_at is not None:
                raise AdministrativeError(409, "object_archived", "Restore the project first")
        return resource

    async def target(
        self,
        actor_id: UUID,
        target_id: UUID,
        organization_id: UUID | None = None,
        *,
        active: bool = True,
    ) -> User | None:
        user = await self.domain.get_user(target_id)
        if active and (user is None or not user.is_active):
            raise AdministrativeError(422, "invalid_member", "An active user is required")
        try:
            await self.roles.require_lower_level(actor_id, target_id)
        except PermissionDeniedError as exc:
            raise AdministrativeError(403, "membership_hierarchy", str(exc)) from exc
        if organization_id is not None and not await self.roles.can_manage(
            actor_id, organization_id
        ):
            if await self.roles.level(target_id) > 0:
                raise AdministrativeError(
                    403, "membership_hierarchy", "Project managers can manage only employees"
                )
        if active and organization_id is not None:
            member = await self.domain.get_organization_member(organization_id, target_id)
            if member is None or member.state != "active":
                raise AdministrativeError(
                    422, "invalid_member", "An active organization member is required"
                )
        return user

    async def member(self, scope: Scope, scope_id: UUID, target_id: UUID) -> Membership | None:
        return (
            await self.domain.get_organization_member(scope_id, target_id)
            if scope == "organization"
            else await self.domain.get_project_member(scope_id, target_id)
        )

    @staticmethod
    def response(member: Membership, user: User) -> MembershipResponse:
        return MembershipResponse(
            user=MemberUser(
                id=user.id,
                first_name=user.profile.first_name,
                last_name=user.profile.last_name,
                is_active=user.is_active,
            ),
            role=member.role,
            state=member.state,
        )

    def audit(
        self,
        actor_id: UUID,
        scope: Scope,
        scope_id: UUID,
        target_id: UUID,
        old_state: str | None,
        old_role: str | None,
        new_state: str,
        new_role: str,
    ) -> None:
        action: Literal["member_removed", "member_added", "member_role_changed"] = (
            "member_removed"
            if new_state == "revoked"
            else "member_added"
            if old_state != "active"
            else "member_role_changed"
        )
        audit = self.audit_writer
        entities: tuple[tuple[Literal["organization", "project", "user"], UUID], ...] = (
            (scope, scope_id),
            ("user", target_id),
        )
        for entity_type, entity_id in entities:
            audit.record(
                AdministrativeAuditWrite(
                    actor_id=actor_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    subject_user_id=target_id,
                    action=action,
                    changes=(
                        AuditChange(
                            field="organization_id" if scope == "organization" else "project_id",
                            old=None if old_state != "active" else scope_id,
                            new=scope_id if new_state == "active" else None,
                        ),
                        AuditChange(field="state", old=old_state, new=new_state),
                        AuditChange(field="role", old=old_role, new=new_role),
                    ),
                )
            )

    async def apply(
        self,
        actor_id: UUID,
        scope: Scope,
        scope_id: UUID,
        target_id: UUID,
        role: Literal["member", "manager"],
    ) -> MembershipResponse:
        resource = await self.resource(actor_id, scope, scope_id, mutate=True)
        org_id = resource.organization_id if isinstance(resource, Project) else resource.id
        user = await self.target(actor_id, target_id, org_id if scope == "project" else None)
        assert user is not None
        member = await self.member(scope, scope_id, target_id)
        old_state, old_role = (member.state, member.role) if member else (None, None)
        if role == "manager" or (old_state == "active" and old_role == "manager"):
            if not await self.roles.can_manage(actor_id, org_id if scope == "project" else None):
                raise AdministrativeError(
                    403, "permission_denied", "Manager role administration required"
                )
        if old_state != "active" or old_role != role:
            if member is None:
                member = (
                    await self.domain.add_organization_member(scope_id, target_id)
                    if scope == "organization"
                    else await self.domain.add_project_member(scope_id, target_id)
                )
            member.state, member.role = "active", role
            self.audit(actor_id, scope, scope_id, target_id, old_state, old_role, "active", role)
            if old_state != "active":
                record_event(
                    self.session,
                    "membership_added",
                    actor_id=actor_id,
                    target_type=scope,
                    target_id=scope_id,
                    organization_id=org_id,
                    member_id=target_id,
                )
        assert member is not None
        return self.response(member, user)

    async def put(
        self,
        actor_id: UUID,
        scope: Scope,
        scope_id: UUID,
        target_id: UUID,
        role: Literal["member", "manager"],
    ) -> MembershipResponse:
        await self.lock(actor_id)
        result = await self.apply(actor_id, scope, scope_id, target_id, role)
        await self.session.commit()
        return result

    async def remove(self, actor_id: UUID, scope: Scope, scope_id: UUID, target_id: UUID) -> None:
        await self.lock(actor_id)
        resource = await self.resource(actor_id, scope, scope_id, mutate=True)
        await self.target(
            actor_id,
            target_id,
            resource.organization_id if isinstance(resource, Project) else None,
            active=False,
        )
        member = await self.member(scope, scope_id, target_id)
        if member is not None and member.state != "revoked":
            self.audit(
                actor_id, scope, scope_id, target_id, member.state, member.role, "revoked", "member"
            )
            if scope == "organization":
                await self.domain.remove_organization_member(scope_id, target_id)
            else:
                await self.domain.remove_project_member(scope_id, target_id)
            record_event(
                self.session,
                "membership_removed",
                actor_id=actor_id,
                target_type=scope,
                target_id=scope_id,
                organization_id=resource.organization_id
                if isinstance(resource, Project)
                else resource.id,
                member_id=target_id,
            )
        await self.session.commit()

    async def page(
        self,
        actor_id: UUID,
        scope: Scope,
        scope_id: UUID,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> MembershipPage:
        resource = await self.resource(actor_id, scope, scope_id)
        state = state or ("archived" if resource.archived_at else "active")
        prefix = [scope, str(scope_id), state]
        after = None
        if cursor:
            try:
                payload = json.loads(base64.urlsafe_b64decode(cursor))
                if not isinstance(payload, list) or len(payload) != 4 or payload[:3] != prefix:
                    raise ValueError
                after = UUID(payload[3])
            except (ValueError, TypeError, AttributeError, binascii.Error) as exc:
                raise AdministrativeError(422, "invalid_cursor", "Invalid cursor") from exc
        rows = await self.repository.page(scope, scope_id, state, after, limit)
        items = [self.response(member, user) for member, user in rows[:limit]]
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps([*prefix, str(items[-1].user.id)]).encode()
            ).decode()
            if len(rows) > limit
            else None
        )
        return MembershipPage(items=items, next_cursor=next_cursor)
