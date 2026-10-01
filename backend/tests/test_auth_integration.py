"""Optional PostgreSQL/Redis concurrency checks; use only a disposable migrated database."""

import asyncio
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import User
from app.models.registration import PendingRegistration
from app.schemas.domain import RegisterRequest, VerifyEmailRequest
from app.services.auth import AuthService
from app.services.auth_protection import AuthLimiter, ThrottledError
from app.services.registration_mail import RegistrationMailService
from app.services.verification import InvalidVerificationError, create_verification_token

PASSWORD = "a unique integration passphrase"


@pytest.fixture
async def postgres_sessions():
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL must point to a disposable, migrated PostgreSQL database")
    engine = create_async_engine(url, hide_parameters=True)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def request_registration(sessions, email):
    async with sessions() as session:
        await AuthService(session).register(
            RegisterRequest(
                email=email, password=PASSWORD, first_name="Integration", last_name="Test"
            )
        )
        registration = await session.scalar(
            select(PendingRegistration)
            .where(PendingRegistration.email == email)
            .order_by(PendingRegistration.expires_at.desc())
        )
        return create_verification_token(registration)


async def confirm(sessions, token):
    async with sessions() as session:
        await AuthService(session).verify_email(VerifyEmailRequest(token=token, password=PASSWORD))


async def test_postgres_confirmation_is_single_use_under_concurrency(postgres_sessions):
    email = f"{uuid4()}@example.com"
    token = await request_registration(postgres_sessions, email)
    results = await asyncio.gather(
        *[confirm(postgres_sessions, token) for _ in range(8)], return_exceptions=True
    )
    assert results.count(None) == 1
    assert sum(isinstance(r, InvalidVerificationError) for r in results) == 7
    async with postgres_sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(User).where(User.email == email))
            == 1
        )


async def test_postgres_two_confirmed_requests_preserve_one_account(postgres_sessions):
    email = f"{uuid4()}@example.com"
    tokens = [await request_registration(postgres_sessions, email) for _ in range(2)]
    await asyncio.gather(*[confirm(postgres_sessions, token) for token in tokens])
    async with postgres_sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(User).where(User.email == email))
            == 1
        )


async def test_postgres_mail_workers_skip_locked_rows(postgres_sessions, monkeypatch):
    email = f"{uuid4()}@example.com"
    await request_registration(postgres_sessions, email)
    sent = []

    def send(registration):
        time.sleep(0.05)
        sent.append(registration.id)

    monkeypatch.setattr("app.services.registration_mail.send_confirmation", send)

    async def process():
        async with postgres_sessions() as session:
            return await RegistrationMailService(session).process_one()

    results = await asyncio.gather(process(), process())
    assert results.count(True) == 1
    assert len(sent) == 1
    async with postgres_sessions() as session:
        row = await session.scalar(
            select(PendingRegistration).where(PendingRegistration.email == email)
        )
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        await RegistrationMailService(session).process_one()
        assert (
            await session.scalar(
                select(PendingRegistration).where(PendingRegistration.email == email)
            )
            is None
        )


async def test_real_redis_atomic_limits_across_connections(tmp_path, monkeypatch):
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("redis-server is not installed")
    socket = tmp_path / "redis.sock"
    process = subprocess.Popen(
        [
            executable,
            "--port",
            "0",
            "--unixsocket",
            str(socket),
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    monkeypatch.setattr(get_settings(), "login_account_limit", 5)
    monkeypatch.setattr(get_settings(), "auth_window_seconds", 1)
    try:
        for _ in range(100):
            if socket.exists():
                break
            await asyncio.sleep(0.01)
        async with Redis(unix_socket_path=str(socket), decode_responses=True) as first:
            async with Redis(unix_socket_path=str(socket), decode_responses=True) as second:
                limiters = [AuthLimiter(first), AuthLimiter(second)]
                outcomes = await asyncio.gather(
                    *[
                        limiters[i % 2].check("login", "same-account", f"192.0.2.{i}")
                        for i in range(50)
                    ],
                    return_exceptions=True,
                )
                assert outcomes.count(None) == 5
                assert sum(isinstance(o, ThrottledError) for o in outcomes) == 45
                await asyncio.sleep(1.05)
                await limiters[0].check("login", "same-account", "192.0.2.99")
    finally:
        process.terminate()
        process.wait(timeout=5)
