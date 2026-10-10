import asyncio
import hashlib
import logging
from unittest.mock import patch

import pytest
from auth_helpers import seed_account
from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient
from redis.exceptions import ConnectionError
from sqlalchemy import select

from app.core.config import get_settings
from app.dependencies.auth_protection import auth_limiter
from app.main import app
from app.models import User, UserProfile
from app.models.registration import PendingRegistration
from app.services.auth import password_hash
from app.services.auth_protection import (
    AuthLimiter,
    AuthUnavailableError,
    PasswordPolicyError,
    ThrottledError,
    client_address,
    normalize_address,
    validate_password,
)

PASSWORD = "correct horse battery staple"


async def login(client: AsyncClient, email: str = "user@example.com", password: str = PASSWORD):
    return await client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.mark.parametrize(
    "password",
    ["short", "a" * 11, " " * 12, "\t" * 15, "p" * 129, "password123456", "Password123!"],
)
async def test_weak_passwords_rejected_without_echo(client, password):
    with pytest.raises(PasswordPolicyError):
        await validate_password(password)


async def test_offline_corpus_and_failure(tmp_path, monkeypatch):
    corpus = tmp_path / "passwords.sha256"
    corpus.write_text(hashlib.sha256(b"a compromised passphrase").hexdigest() + "\n")
    monkeypatch.setattr(get_settings(), "breached_password_file", str(corpus))
    with pytest.raises(PasswordPolicyError, match="compromised"):
        await validate_password("a compromised passphrase")
    await validate_password("a different long passphrase")
    monkeypatch.setattr(get_settings(), "breached_password_file", str(tmp_path / "missing"))
    with pytest.raises(AuthUnavailableError):
        await validate_password(PASSWORD)


async def test_argon2_and_legacy_password_still_work(client, db_session):
    await seed_account("user@example.com")
    pending = await db_session.scalar(select(User))
    assert pending.password_hash.startswith("$argon2id$")
    assert pending.password_hash != PASSWORD
    legacy = User(
        email="legacy@example.com",
        password_hash=password_hash.hash("short"),
        profile=UserProfile(first_name="Legacy", last_name="User"),
    )
    db_session.add(legacy)
    await db_session.commit()
    assert (await login(client, "legacy@example.com", "short")).status_code == 200


async def test_equivalent_hash_work_and_uniform_401(client, db_session):
    await seed_account("user@example.com")
    user = await db_session.scalar(select(User))
    responses = []
    with patch.object(password_hash, "verify", wraps=password_hash.verify) as verify:
        responses.append(await login(client, password="wrong"))
        responses.append(await login(client, "unknown@example.com", "wrong"))
        user.is_active = False
        await db_session.commit()
        responses.append(await login(client))
        assert verify.call_count == 3
        assert [call.args[1] for call in verify.call_args_list] == [
            user.password_hash,
            get_settings().auth_dummy_hash,
            user.password_hash,
        ]
    assert (await login(client, password="")).status_code == 422
    assert all(r.status_code == 401 for r in responses)
    assert all(r.json() == responses[0].json() for r in responses)


async def test_invalid_token_is_rejected(client):
    response = await client.get("/api/organizations", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("::ffff:192.0.2.1", "192.0.2.1"),
        ("2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        ("fe80::1%eth0", "fe80::1"),
        ("not-an-ip", "unknown"),
    ],
)
def test_address_normalization(source, expected):
    assert normalize_address(source) == expected


def test_proxy_headers_require_explicit_trust(monkeypatch):
    assert client_address("192.0.2.1", "198.51.100.1") == "192.0.2.1"
    monkeypatch.setattr(get_settings(), "trusted_proxy_networks", ["10.0.0.0/8"])
    assert client_address("10.0.0.1", "fake, 198.51.100.1, 10.0.0.2") == "198.51.100.1"
    assert client_address("10.0.0.1", "fake") == "unknown"


async def test_atomic_distributed_limits_and_window_reset(monkeypatch):
    monkeypatch.setattr(get_settings(), "login_account_limit", 4)
    async with FakeRedis(decode_responses=True) as redis:
        limiters = [AuthLimiter(redis), AuthLimiter(redis)]
        outcomes = await asyncio.gather(
            *[limiters[i % 2].check("login", "a@example.com", f"192.0.2.{i}") for i in range(30)],
            return_exceptions=True,
        )
        assert outcomes.count(None) == 4
        assert sum(isinstance(o, ThrottledError) for o in outcomes) == 26
        keys = await redis.keys("*:account:*")
        assert len(keys) == 1
        assert int(await redis.get(keys[0])) == 4
        assert 0 < await redis.ttl(keys[0]) <= 900
        # Expiring the fixed-window counter permits another attempt.
        await redis.expire(keys[0], 0)
        await limiters[0].check("login", "a@example.com", "192.0.2.99")


async def test_address_budget_shared_across_accounts(monkeypatch):
    monkeypatch.setattr(get_settings(), "login_address_limit", 2)
    async with FakeRedis(decode_responses=True) as redis:
        limiter = AuthLimiter(redis)
        await limiter.check("login", "a", "::ffff:192.0.2.1")
        await limiter.check("login", "b", "192.0.2.1")
        with pytest.raises(ThrottledError):
            await limiter.check("login", "c", "192.0.2.1")
        assert len(await redis.keys("*:account:*")) == 2


async def test_login_429_normalization_and_success_does_not_reset(client, monkeypatch):
    await seed_account("user@example.com")
    monkeypatch.setattr(get_settings(), "login_account_limit", 2)
    assert (await login(client)).status_code == 200
    assert (await login(client, "USER@example.com", "wrong")).status_code == 401
    response = await login(client, " user@example.com ")
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 900


@pytest.mark.parametrize("endpoint", ["login"])
async def test_redis_outage_fails_closed(client, db_session, endpoint):
    class UnavailableRedis:
        async def eval(self, *args):
            raise ConnectionError("sensitive infrastructure details")

    app.dependency_overrides[auth_limiter] = lambda: AuthLimiter(UnavailableRedis())
    response = await login(client)
    assert response.status_code == 503
    assert "sensitive" not in response.text
    assert await db_session.scalar(select(User)) is None
    assert await db_session.scalar(select(PendingRegistration)) is None


async def test_security_logs_do_not_contain_credentials(client, caplog):
    with caplog.at_level(logging.INFO, logger="security.auth"):
        await seed_account("user@example.com")
        await login(client)
        await login(client, password="wrong")
    assert "login_success" in caplog.text
    assert "credentials_invalid" in caplog.text
    assert PASSWORD not in caplog.text
    assert "user@example.com" not in caplog.text
    assert "$argon2" not in caplog.text


def test_security_settings_reject_unsafe_values():
    from pydantic import ValidationError

    from app.core.config import Settings

    for extra in [
        {"login_account_limit": 0},
        {"auth_dummy_hash": "bad"},
        {"trusted_proxy_networks": ["0.0.0.0/0"]},
        {"public_app_url": "https://example.com/#bad"},
    ]:
        with pytest.raises((ValidationError, ValueError)):
            Settings(database_url="sqlite+aiosqlite://", **extra)


@pytest.mark.parametrize("content", ["", "not a sha256 digest", "non-ascii: é"])
async def test_malformed_offline_corpus_fails_closed(tmp_path, monkeypatch, content):
    corpus = tmp_path / "broken.sha256"
    corpus.write_text(content)
    monkeypatch.setattr(get_settings(), "breached_password_file", str(corpus))
    with pytest.raises(AuthUnavailableError):
        await validate_password(PASSWORD)
