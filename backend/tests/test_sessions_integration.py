"""Run against a disposable PostgreSQL database migrated to head."""

import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.models import User
from app.models.auth_session import PasswordReset
from app.schemas.domain import LoginRequest, OrganizationCreate
from app.services.auth import AuthService
from app.services.domain import DomainService
from app.services.errors import InvalidCredentialsError, PermissionDeniedError
from app.services.sessions import SessionService, reset_token
from tests.test_auth_integration import (
    PASSWORD,
    confirm,
    request_registration,
)
from tests.test_auth_integration import postgres_sessions as pg_sessions

postgres_sessions = pg_sessions


async def create_account(sessions):
    email = f"{uuid4()}@example.com"
    token = await request_registration(sessions, email)
    await confirm(sessions, token)
    async with sessions() as session:
        access, refresh, user = await AuthService(session).login(
            LoginRequest(email=email, password=PASSWORD)
        )
        return email, user.id, access, refresh


async def test_postgres_refresh_replay_race_revokes_family(postgres_sessions):
    _, _, access, refresh = await create_account(postgres_sessions)

    async def rotate():
        async with postgres_sessions() as session:
            return await SessionService(session).refresh(refresh)

    results = await asyncio.gather(*[rotate() for _ in range(8)], return_exceptions=True)
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert sum(isinstance(result, InvalidCredentialsError) for result in results) == 7
    async with postgres_sessions() as session:
        for token in (access, next(result[0] for result in results if isinstance(result, tuple))):
            try:
                await SessionService(session).authenticate(token)
            except InvalidCredentialsError:
                pass
            else:
                raise AssertionError("Replay must revoke even the winning refresh access token")


async def test_postgres_password_change_serializes_with_login(postgres_sessions):
    email, user_id, access, _ = await create_account(postgres_sessions)

    async def login():
        async with postgres_sessions() as session:
            return await AuthService(session).login(LoginRequest(email=email, password=PASSWORD))

    async def change():
        async with postgres_sessions() as session:
            await AuthService(session).change_password(
                user_id, PASSWORD, "a new secure integration phrase"
            )

    results = await asyncio.gather(login(), change(), return_exceptions=True)
    assert results[1] is None
    assert isinstance(results[0], (tuple, InvalidCredentialsError))
    tokens = [access] + ([results[0][0]] if isinstance(results[0], tuple) else [])
    async with postgres_sessions() as session:
        for token in tokens:
            try:
                await SessionService(session).authenticate(token)
            except InvalidCredentialsError:
                pass
            else:
                raise AssertionError("Old-password login escaped password-change revocation")


async def test_postgres_reset_is_single_use_under_concurrency(postgres_sessions):
    email, _, _, _ = await create_account(postgres_sessions)
    async with postgres_sessions() as session:
        await AuthService(session).request_password_reset(email)
        pending = await session.scalar(select(PasswordReset).where(PasswordReset.email == email))
        token = reset_token(pending.id)

    async def reset():
        async with postgres_sessions() as session:
            await AuthService(session).reset_password(token, "a reset integration passphrase")

    results = await asyncio.gather(*[reset() for _ in range(6)], return_exceptions=True)
    assert results.count(None) == 1
    assert sum(isinstance(r, InvalidCredentialsError) for r in results) == 5


async def test_postgres_employee_cannot_create_organization_or_self_deactivate(postgres_sessions):
    _, user_id, _, _ = await create_account(postgres_sessions)

    async def create():
        async with postgres_sessions() as session:
            return await DomainService(session).create_organization(
                user_id, OrganizationCreate(name="Race")
            )

    async def deactivate():
        async with postgres_sessions() as session:
            await AuthService(session).deactivate(user_id, PASSWORD)

    created, deactivated = await asyncio.gather(create(), deactivate(), return_exceptions=True)
    async with postgres_sessions() as session:
        user = await session.get(User, user_id)
        assert user.is_active
        assert isinstance(deactivated, PermissionDeniedError)
        assert isinstance(created, PermissionDeniedError)
