import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.models import (
    AdministrativeAuditEvent,
    Organization,
    OrganizationMember,
    ProjectMember,
    User,
    UserProfile,
)
from app.schemas.domain import OrganizationCreate, ProjectCreate, StatusCreate
from app.services.administration import AdministrationService
from app.services.auth import password_hash
from app.services.bootstrap import bootstrap_administrator
from app.services.domain import DomainService
from app.services.errors import PermissionDeniedError


def settings(email="local administrator", password="x"):
    return get_settings().model_copy(
        update={
            "admin_email": email,
            "admin_password": SecretStr(password),
        }
    )


@pytest.mark.parametrize(
    "name,value", [("ADMIN_EMAIL", ""), ("ADMIN_EMAIL", "  "), ("ADMIN_PASSWORD", "")]
)
def test_empty_configuration_rejected_without_disclosure(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("name", ["ADMIN_EMAIL", "ADMIN_PASSWORD"])
def test_missing_configuration_rejected(monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


async def test_bootstrap_login_idempotency_and_credentials_protection(client, db_session):
    config = settings(password="a" * 140)
    await bootstrap_administrator(db_session, config)
    user = await db_session.scalar(select(User))
    assert user.is_system_admin and user.is_active and not user.must_change_password
    assert user.profile.first_name == user.profile.last_name == ""
    response = await client.post(
        "/api/auth/login",
        json={
            "email": " LOCAL ADMINISTRATOR ",
            "password": "a" * 140,
        },
    )
    assert response.status_code == 200
    assert response.json()["user"]["is_system_admin"] is True
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    count = await db_session.scalar(select(func.count()).select_from(AdministrativeAuditEvent))
    await db_session.rollback()
    await bootstrap_administrator(db_session, config)
    assert (
        await db_session.scalar(select(func.count()).select_from(AdministrativeAuditEvent)) == count
    )
    assert (await client.get("/api/organizations", headers=headers)).status_code == 200
    for path, data in [
        (
            "password/change",
            {"current_password": "a" * 140, "new_password": "replacement password"},
        ),
        ("deactivate", {"current_password": "x"}),
    ]:
        response = await client.post("/api/auth/" + path, headers=headers, json=data)
        assert response.status_code == 403
    # No public system-role mutation or ownership-transfer alias exists.
    assert (
        await client.patch(
            f"/api/users/{user.id}", headers=headers, json={"is_system_admin": False}
        )
    ).status_code == 404
    await db_session.rollback()
    await bootstrap_administrator(db_session, settings(password="changed"))
    assert (await client.get("/api/organizations", headers=headers)).status_code == 401


async def test_bootstrap_switch_preserves_memberships_and_unblocks(db_session):
    await bootstrap_administrator(db_session, settings())
    previous = await db_session.scalar(select(User))
    previous_id = previous.id
    organization = Organization(name="Retained")
    db_session.add(organization)
    await db_session.flush()
    db_session.add(
        OrganizationMember(
            organization_id=organization.id, user_id=previous.id, role="manager", state="active"
        )
    )
    replacement = User(
        email="replacement",
        password_hash=password_hash.hash("old"),
        is_active=False,
        must_change_password=True,
        profile=UserProfile(first_name="Existing", last_name="Profile"),
    )
    db_session.add(replacement)
    await db_session.flush()
    replacement_id = replacement.id
    db_session.add(
        OrganizationMember(
            organization_id=organization.id, user_id=replacement.id, role="manager", state="revoked"
        )
    )
    await db_session.commit()
    await bootstrap_administrator(db_session, settings("replacement"))
    assert not (await db_session.get(User, previous_id)).is_system_admin
    assert (
        replacement.is_system_admin
        and replacement.is_active
        and not replacement.must_change_password
    )
    assert replacement.profile.first_name == "Existing"
    memberships = list(
        await db_session.scalars(select(OrganizationMember).order_by(OrganizationMember.user_id))
    )
    assert {(m.user_id, m.role, m.state) for m in memberships} == {
        (previous_id, "manager", "active"),
        (replacement_id, "manager", "revoked"),
    }


async def test_global_level_ignores_inactive_memberships(db_session):
    user = User(
        email="manager@example.com",
        password_hash="unused",
        profile=UserProfile(first_name="M", last_name="M"),
    )
    org = Organization(name="O")
    db_session.add_all([user, org])
    await db_session.flush()
    member = OrganizationMember(
        organization_id=org.id, user_id=user.id, role="manager", state="archived"
    )
    db_session.add(member)
    await db_session.commit()
    service = AdministrationService(db_session)
    assert await service.level(user.id) == 0
    member.state = "active"
    await db_session.flush()
    assert await service.level(user.id) == 2
    member.state = "revoked"
    user.is_system_admin = True
    await db_session.flush()
    assert await service.level(user.id) == 3
    await service.require_lower_level(user.id, user.id)


async def test_creation_without_members_and_scoped_workflow(db_session):
    await bootstrap_administrator(db_session, settings())
    admin = await db_session.scalar(select(User))
    service = DomainService(db_session)
    org = await service.create_organization(admin.id, OrganizationCreate(name="Empty"))
    project = await service.create_project(
        admin.id, ProjectCreate(organization_id=org.id, name="Empty")
    )
    assert await db_session.scalar(select(func.count()).select_from(OrganizationMember)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProjectMember)) == 0
    user = User(
        email="pm@example.com",
        password_hash="unused",
        profile=UserProfile(first_name="P", last_name="M"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(OrganizationMember(organization_id=org.id, user_id=user.id))
    member = ProjectMember(project_id=project.id, user_id=user.id, role="manager")
    db_session.add(member)
    await db_session.commit()
    await service.create_status(user.id, project.id, StatusCreate(name="Review"))
    assert (
        await db_session.scalar(
            select(AdministrativeAuditEvent).where(
                AdministrativeAuditEvent.action == "workflow_changed"
            )
        )
        is not None
    )
    member.role = "member"
    await db_session.commit()
    with pytest.raises(PermissionDeniedError):
        await service.create_status(user.id, project.id, StatusCreate(name="Denied"))


async def test_startup_runs_bootstrap_before_health(client, db_session, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app import main

    monkeypatch.setattr(
        main, "SessionFactory", async_sessionmaker(db_session.bind, expire_on_commit=False)
    )
    monkeypatch.setattr(main, "settings", settings())
    async with main.lifespan(main.app):
        assert await db_session.scalar(select(User.is_system_admin)) is True
        assert (await client.get("/health")).status_code == 200


async def test_bootstrap_audit_failure_rolls_back_every_change(db_session, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    from app.services.administrative_audit import AdministrativeAuditService

    def reject(self, data):
        self.repository.add(AdministrativeAuditEvent(actor_kind="invalid"))

    monkeypatch.setattr(AdministrativeAuditService, "record", reject)
    with pytest.raises(IntegrityError):
        await bootstrap_administrator(db_session, settings())
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
    assert await db_session.scalar(select(func.count()).select_from(AdministrativeAuditEvent)) == 0


async def test_admin_own_membership_and_non_email_identifier(client, db_session):
    await bootstrap_administrator(db_session, settings())
    login = await client.post(
        "/api/auth/login", json={"email": "local administrator", "password": "x"}
    )
    user_id = login.json()["user"]["id"]
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    org = (await client.post("/api/organizations", headers=headers, json={"name": "Own"})).json()
    project = (
        await client.post(
            "/api/projects", headers=headers, json={"organization_id": org["id"], "name": "Own"}
        )
    ).json()
    for scope, identifier in (("organizations", org["id"]), ("projects", project["id"])):
        url = f"/api/{scope}/{identifier}/members"
        for _ in range(2):
            response = await client.post(
                url, headers=headers, json={"email": "local administrator"}
            )
            assert response.status_code == 200
        for _ in range(2):
            assert (await client.delete(f"{url}/{user_id}", headers=headers)).status_code == 200
        assert (
            await client.post(url, headers=headers, json={"email": "local administrator"})
        ).status_code == 200
    # Re-add reuses the pair, never duplicates it or strips the system role.
    assert await db_session.scalar(select(func.count()).select_from(OrganizationMember)) == 1
    assert await db_session.scalar(select(func.count()).select_from(ProjectMember)) == 1
    assert await db_session.scalar(select(User.is_system_admin)) is True


async def test_switch_revokes_old_sessions_and_pending_email_actions(db_session):
    from datetime import UTC, datetime, timedelta

    from app.models.auth_session import PasswordReset
    from app.models.registration import PendingRegistration
    from app.schemas.domain import LoginRequest
    from app.services.auth import AuthService
    from app.services.errors import InvalidCredentialsError
    from app.services.sessions import SessionService

    await bootstrap_administrator(db_session, settings("old@example.com"))
    access, refresh, old = await AuthService(db_session).login(
        LoginRequest(email="old@example.com", password="x")
    )
    now = datetime.now(UTC)
    db_session.add(
        PasswordReset(
            user_id=old.id,
            email=old.email,
            token_hash="synthetic",
            expires_at=now + timedelta(hours=1),
            next_attempt_at=now,
        )
    )
    db_session.add(
        PendingRegistration(
            email=old.email,
            password_hash="unused",
            first_name="Old",
            last_name="Old",
            expires_at=now + timedelta(hours=1),
            next_attempt_at=now,
        )
    )
    await db_session.commit()
    await bootstrap_administrator(db_session, settings("new@example.com"))
    assert await db_session.scalar(select(PasswordReset)) is None
    assert await db_session.scalar(select(PendingRegistration)) is None
    with pytest.raises(InvalidCredentialsError):
        await SessionService(db_session).authenticate(access)
    with pytest.raises(InvalidCredentialsError):
        await SessionService(db_session).refresh(refresh)
    assert not old.is_system_admin
    assert password_hash.verify("x", old.password_hash)


async def test_stale_request_cannot_mutate_after_bootstrap_revocation(db_session):
    from app.models.auth_session import AuthSession
    from app.schemas.domain import LoginRequest
    from app.services.auth import AuthService
    from app.services.errors import InvalidCredentialsError

    await bootstrap_administrator(db_session, settings("old@example.com"))
    _, _, user = await AuthService(db_session).login(
        LoginRequest(email="old@example.com", password="x")
    )
    session_id = await db_session.scalar(select(AuthSession.id))
    user_id = user.id
    await db_session.commit()
    await bootstrap_administrator(db_session, settings("new@example.com"))
    db_session.info["authenticated_session_id"] = session_id
    with pytest.raises(InvalidCredentialsError):
        await AuthService(db_session).change_password(user_id, "x", "another secure password")
    await db_session.rollback()
    with pytest.raises(InvalidCredentialsError):
        await DomainService(db_session).create_organization(
            user_id, OrganizationCreate(name="Denied")
        )
