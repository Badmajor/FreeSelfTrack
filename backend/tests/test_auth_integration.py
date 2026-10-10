"""Optional PostgreSQL/Redis concurrency checks; use only a disposable migrated database."""

import asyncio
import os
import shutil
import subprocess

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services.auth_protection import AuthLimiter, ThrottledError

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
