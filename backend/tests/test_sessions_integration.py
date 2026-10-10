"""Run against a disposable PostgreSQL database migrated to head."""

import asyncio
from uuid import uuid4

from app.models import User, UserProfile
from app.schemas.domain import LoginRequest
from app.services.auth import AuthService, password_hash
from app.services.errors import InvalidCredentialsError
from app.services.sessions import SessionService
from tests.test_auth_integration import PASSWORD
from tests.test_auth_integration import postgres_sessions as pg_sessions

postgres_sessions = pg_sessions


async def create_account(sessions):
    email = f"{uuid4()}@example.com"
    async with sessions() as session:
        session.add(
            User(
                email=email,
                password_hash=password_hash.hash(PASSWORD),
                profile=UserProfile(first_name="Integration", last_name="User"),
            )
        )
        await session.commit()
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
