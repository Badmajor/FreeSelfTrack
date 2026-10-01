import asyncio
import hashlib
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from auth_helpers import confirm_registration, confirmation_token
from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient
from redis.exceptions import ConnectionError
from sqlalchemy import select

from app.core.config import get_settings
from app.dependencies.auth_protection import auth_limiter
from app.main import app
from app.models import User, UserProfile
from app.models.registration import PendingRegistration
from app.services.auth import AuthService, password_hash
from app.services.auth_protection import (
    AuthLimiter,
    AuthUnavailableError,
    PasswordPolicyError,
    ThrottledError,
    client_address,
    normalize_address,
    validate_password,
)
from app.services.registration_mail import RegistrationMailService, send_confirmation
from app.services.verification import create_verification_token, verification_key

PASSWORD = "correct horse battery staple"


async def register(client: AsyncClient, email: str = "user@example.com", **extra):
    return await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Test",
            "last_name": "User",
            **extra,
        },
    )


async def login(client: AsyncClient, email: str = "user@example.com", password: str = PASSWORD):
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def test_registration_is_uniform_and_requires_confirmation(client, db_session):
    first = await register(client, " User@example.com ")
    assert first.status_code == 202
    assert set(first.json()) == {"message"}
    assert await db_session.scalar(select(User)) is None
    assert (await login(client)).status_code == 401
    await confirm_registration(client, "user@example.com")
    success = await login(client, "USER@example.com")
    assert success.status_code == 200
    assert success.json()["user"]["email"] == "user@example.com"
    assert success.json()["user"]["profile"]["first_name"] == "Test"
    assert "password" not in success.text
    duplicate = await register(client, "USER@example.com", password="another safe passphrase")
    assert duplicate.status_code == first.status_code
    assert duplicate.json() == first.json()
    await confirm_registration(client, "user@example.com", "another safe passphrase")
    assert (await login(client)).status_code == 200
    assert (await login(client, password="another safe passphrase")).status_code == 401


@pytest.mark.parametrize(
    "password",
    ["short", "a" * 11, " " * 12, "\t" * 15, "p" * 129, "password123456", "Password123!"],
)
async def test_weak_passwords_rejected_without_echo(client, password):
    response = await register(client, password=password)
    assert response.status_code == 422
    assert "input" not in response.text
    assert "password_hash" not in response.text


async def test_email_validation_does_not_echo_other_fields(client):
    response = await register(client, "invalid", password=PASSWORD)
    assert response.status_code == 422
    assert PASSWORD not in response.text


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
    await register(client)
    pending = await db_session.scalar(select(PendingRegistration))
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
    await register(client)
    await confirm_registration(client, "user@example.com")
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
    responses.append(await login(client, password=""))
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
    await register(client)
    await confirm_registration(client, "user@example.com")
    monkeypatch.setattr(get_settings(), "login_account_limit", 2)
    assert (await login(client)).status_code == 200
    assert (await login(client, "USER@example.com", "wrong")).status_code == 401
    response = await login(client, " user@example.com ")
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 900


async def test_register_is_throttled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "register_account_limit", 1)
    assert (await register(client)).status_code == 202
    response = await register(client, "USER@example.com")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.parametrize("endpoint", ["login", "register", "verify-email"])
async def test_redis_outage_fails_closed(client, db_session, endpoint):
    class UnavailableRedis:
        async def eval(self, *args):
            raise ConnectionError("sensitive infrastructure details")

    app.dependency_overrides[auth_limiter] = lambda: AuthLimiter(UnavailableRedis())
    if endpoint == "register":
        response = await register(client)
    elif endpoint == "login":
        response = await login(client)
    else:
        response = await client.post(
            "/api/auth/verify-email", json={"token": "bad", "password": ""}
        )
    assert response.status_code == 503
    assert "sensitive" not in response.text
    assert await db_session.scalar(select(User)) is None
    assert await db_session.scalar(select(PendingRegistration)) is None


async def test_confirmation_requires_password_and_rejects_replay(client):
    await register(client)
    token = await confirmation_token("user@example.com")
    wrong = await client.post("/api/auth/verify-email", json={"token": token, "password": "wrong"})
    assert wrong.status_code == 400
    assert (await login(client)).status_code == 401
    await confirm_registration(client, "user@example.com")
    replay = await client.post(
        "/api/auth/verify-email", json={"token": token, "password": PASSWORD}
    )
    assert replay.status_code == 400
    assert (await login(client)).status_code == 200


async def test_confirmation_invalid_expired_and_wrong_token_purpose(client, db_session):
    await register(client)
    pending = await db_session.scalar(select(PendingRegistration))
    expired = jwt.encode(
        {
            "sub": str(pending.id),
            "exp": datetime.now(UTC) - timedelta(seconds=1),
            "aud": "email-verification",
        },
        verification_key(),
        algorithm="HS256",
    )
    for token in ["broken", expired, AuthService.create_access_token(uuid4())]:
        response = await client.post(
            "/api/auth/verify-email", json={"token": token, "password": PASSWORD}
        )
        assert response.status_code == 400
        assert token not in response.text
    token = create_verification_token(pending)
    response = await client.get("/api/organizations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    response = await client.post(
        "/api/auth/verify-email", json={"token": token, "password": PASSWORD}
    )
    assert response.status_code == 400


async def test_multiple_pending_registrations_do_not_overwrite_owner(client):
    await register(client, password="attacker chosen passphrase")
    attacker_token = await confirmation_token("user@example.com")
    await register(client)
    await confirm_registration(client, "user@example.com")
    response = await client.post(
        "/api/auth/verify-email",
        json={"token": attacker_token, "password": "attacker chosen passphrase"},
    )
    assert response.status_code == 200
    assert (await login(client)).status_code == 200
    assert (await login(client, password="attacker chosen passphrase")).status_code == 401


async def test_mail_retry_delivery_and_cleanup(client, db_session, caplog):
    await register(client)
    pending = await db_session.scalar(select(PendingRegistration))
    service = RegistrationMailService(db_session)
    with patch(
        "app.services.registration_mail.send_confirmation",
        side_effect=smtplib.SMTPException("secret"),
    ):
        with caplog.at_level(logging.INFO):
            assert await service.process_one()
    assert pending.attempts == 1
    assert pending.sent_at is None
    assert "secret" not in caplog.text
    assert not await service.process_one()
    pending.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    with patch("app.services.registration_mail.send_confirmation") as send:
        assert await service.process_one()
        send.assert_called_once()
        assert pending.sent_at is not None
        assert not await service.process_one()
    pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert not await service.process_one()
    assert await db_session.scalar(select(PendingRegistration)) is None


async def test_smtp_uses_tls_and_fragment_link(client, db_session):
    await register(client)
    pending = await db_session.scalar(select(PendingRegistration))
    with patch("app.services.registration_mail.smtplib.SMTP") as smtp:
        send_confirmation(pending)
        connection = smtp.return_value
        connection.starttls.assert_called_once()
        message = connection.send_message.call_args.args[0]
        assert message["To"] == "user@example.com"
        assert "/#verify=" in message.get_content()
        assert PASSWORD not in message.get_content()
        assert pending.password_hash not in message.get_content()


async def test_security_logs_do_not_contain_credentials(client, caplog):
    with caplog.at_level(logging.INFO, logger="security.auth"):
        await register(client)
        await login(client)
    assert "registration_accepted" in caplog.text
    assert "credentials_invalid" in caplog.text
    assert PASSWORD not in caplog.text
    assert "user@example.com" not in caplog.text
    assert "$argon2" not in caplog.text


async def test_smtp_delivery_over_socket(client, db_session, monkeypatch):
    """Exercise the actual SMTP client against a local mail sink, without sending externally."""
    received = []

    async def smtp_sink(reader, writer):
        writer.write(b"220 local test mail sink\r\n")
        await writer.drain()
        while line := await reader.readline():
            command = line.decode().strip().upper()
            if command.startswith(("EHLO", "HELO", "MAIL", "RCPT", "RSET")):
                writer.write(b"250 OK\r\n")
            elif command == "DATA":
                writer.write(b"354 End with dot\r\n")
                await writer.drain()
                body = []
                while (data := await reader.readline()) != b".\r\n":
                    if not data:
                        break
                    body.append(data)
                received.append(b"".join(body))
                writer.write(b"250 Queued\r\n")
            elif command == "QUIT":
                writer.write(b"221 Bye\r\n")
                await writer.drain()
                break
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(smtp_sink, "127.0.0.1", 0)
    async with server:
        monkeypatch.setattr(get_settings(), "smtp_host", "127.0.0.1")
        monkeypatch.setattr(get_settings(), "smtp_port", server.sockets[0].getsockname()[1])
        monkeypatch.setattr(get_settings(), "smtp_security", "plain")
        await register(client)
        assert await RegistrationMailService(db_session).process_one()
    assert len(received) == 1
    from email import policy
    from email.parser import BytesParser

    message = BytesParser(policy=policy.default).parsebytes(received[0])
    text = message.get_content()
    token = text.split("/#verify=", 1)[1].split()[0]
    response = await client.post(
        "/api/auth/verify-email", json={"token": token, "password": PASSWORD}
    )
    assert response.status_code == 200
    assert (await login(client)).status_code == 200


async def test_smtp_ssl_checks_certificate(client, db_session, monkeypatch):
    import ssl

    monkeypatch.setattr(get_settings(), "smtp_security", "tls")
    await register(client)
    pending = await db_session.scalar(select(PendingRegistration))
    with patch("app.services.registration_mail.smtplib.SMTP_SSL") as smtp:
        send_confirmation(pending)
        context = smtp.call_args.kwargs["context"]
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname


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
