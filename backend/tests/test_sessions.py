import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.dependencies.session_cookie import REFRESH_COOKIE
from app.models import User
from app.models.auth_session import AuthSession, PasswordReset, RefreshCredential
from app.services.reset_mail import ResetMailService
from app.services.sessions import reset_token, token_digest
from tests.auth_helpers import confirm_registration

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "another excellent horse passphrase"


async def account(client, email="session@example.com"):
    assert (
        await client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "first_name": "Session",
                "last_name": "Tester",
            },
        )
    ).status_code == 202
    await confirm_registration(client, email)
    return await sign_in(client, email)


async def sign_in(client, email="session@example.com", password=PASSWORD):
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response


def bearer(response):
    return {"Authorization": "Bearer " + response.json()["access_token"]}


async def use_refresh(client, token):
    return await client.post("/api/auth/refresh", headers={"Cookie": f"{REFRESH_COOKIE}={token}"})


async def test_rotation_replay_revokes_only_its_family(client, db_session):
    first = await account(client)
    old = client.cookies.get(REFRESH_COOKIE)
    other = await sign_in(client)
    other_cookie = client.cookies.get(REFRESH_COOKIE)
    rotated = await use_refresh(client, old)
    assert rotated.status_code == 200
    current = client.cookies.get(REFRESH_COOKIE)
    assert current != old
    assert (await client.get("/api/organizations", headers=bearer(first))).status_code == 200
    assert (await use_refresh(client, old)).status_code == 401
    assert (await use_refresh(client, current)).status_code == 401
    for response in (first, rotated):
        assert (await client.get("/api/organizations", headers=bearer(response))).status_code == 401
    assert (await client.get("/api/organizations", headers=bearer(other))).status_code == 200
    assert (await use_refresh(client, other_cookie)).status_code == 200
    rows = (await db_session.scalars(select(RefreshCredential))).all()
    assert all(row.token_hash not in {old, current, other_cookie} for row in rows)
    assert any(row.token_hash == token_digest(old) and row.used_at is not None for row in rows)


@pytest.mark.parametrize(
    "method,path", [("post", "/api/auth/logout"), ("delete", "/api/auth/sessions/current")]
)
async def test_logout_immediately_revokes_access_and_refresh(client, method, path):
    first = await account(client)
    old = client.cookies.get(REFRESH_COOKIE)
    response = await getattr(client, method)(path, headers=bearer(first))
    assert response.status_code == 204
    assert client.cookies.get(REFRESH_COOKIE) is None
    assert (await client.get("/api/organizations", headers=bearer(first))).status_code == 401
    assert (await use_refresh(client, old)).status_code == 401


async def test_cookie_attributes_and_csrf(client):
    response = await account(client)
    cookie = response.headers["set-cookie"]
    for attribute in ("Secure", "HttpOnly", "SameSite=strict", "Path=/api/auth"):
        assert attribute in cookie
    assert response.headers["cache-control"] == "no-store"
    for path in ("/api/auth/refresh", "/api/auth/logout", "/api/auth/login"):
        for headers in (
            {"Origin": "https://evil.example"},
            {"Origin": "null"},
            {"Origin": ""},
            {"X-CSRF-Protection": ""},
        ):
            denied = await client.post(
                path, headers=headers, json={"email": "session@example.com", "password": PASSWORD}
            )
            assert denied.status_code == 403
    assert (
        await client.get("/api/organizations")
    ).status_code == 401  # Cookie alone is insufficient.
    assert (await client.post("/api/auth/refresh")).status_code == 200


@pytest.mark.parametrize(
    "claim,value",
    [
        ("aud", "another-api"),
        ("iss", "other"),
        ("type", "refresh"),
        ("sub", "bad-uuid"),
        ("jti", None),
        ("sid", "invalid"),
        ("iat", "123"),
        ("iat", True),
        ("exp", 0),
        ("exp", "9999999999"),
    ],
)
async def test_rejects_invalid_claims(client, claim, value):
    login = await account(client)
    claims = jwt.decode(login.json()["access_token"], options={"verify_signature": False})
    claims[claim] = value
    token = jwt.encode(claims, get_settings().auth_secret_key, algorithm="HS256")
    response = await client.get("/api/organizations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_missing_claims_algorithms_time_and_session_binding(client, db_session):
    login = await account(client)
    claims = jwt.decode(login.json()["access_token"], options={"verify_signature": False})
    variations = [{k: v for k, v in claims.items() if k != omitted} for omitted in claims]
    variations += [
        claims | {"iat": int(datetime.now(UTC).timestamp()) + 100},
        claims | {"sid": str(uuid4())},
        claims | {"sub": str(uuid4())},
        claims | {"iat": claims["exp"]},
        claims | {"exp": claims["iat"] + 9999},
    ]
    tokens = [jwt.encode(c, get_settings().auth_secret_key, algorithm="HS256") for c in variations]
    tokens += [
        jwt.encode(claims, get_settings().auth_secret_key, algorithm="HS384"),
        jwt.encode(claims, "", algorithm="none"),
        "broken",
    ]
    for token in tokens:
        assert (
            await client.get("/api/organizations", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 401
    family = await db_session.scalar(select(AuthSession))
    family.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.get("/api/organizations", headers=bearer(login))).status_code == 401
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_password_change_revokes_every_session_and_pending_reset(client, db_session):
    first = await account(client)
    cookie = client.cookies.get(REFRESH_COOKIE)
    second = await sign_in(client)
    await client.post("/api/auth/password/reset-request", json={"email": "session@example.com"})
    for current, new, expected in (("wrong", NEW_PASSWORD, 401), (PASSWORD, "password1234", 422)):
        response = await client.post(
            "/api/auth/password/change",
            headers=bearer(second),
            json={"current_password": current, "new_password": new},
        )
        assert response.status_code == expected
    assert (
        await client.post(
            "/api/auth/password/change",
            headers=bearer(second),
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
    ).status_code == 204
    for response in (first, second):
        assert (await client.get("/api/organizations", headers=bearer(response))).status_code == 401
    assert (await use_refresh(client, cookie)).status_code == 401
    assert await db_session.scalar(select(PasswordReset)) is None
    assert (
        await client.post(
            "/api/auth/login", json={"email": "session@example.com", "password": PASSWORD}
        )
    ).status_code == 401
    await sign_in(client, password=NEW_PASSWORD)


async def test_reset_request_uniformity_consumption_and_revocation(client, db_session):
    first = await account(client)
    cookie = client.cookies.get(REFRESH_COOKIE)
    second = await sign_in(client)
    responses = [
        await client.post("/api/auth/password/reset-request", json={"email": email})
        for email in ("session@example.com", "unknown@example.com")
    ]
    assert responses[0].status_code == responses[1].status_code == 202
    assert responses[0].json() == responses[1].json()
    pending = await db_session.scalar(select(PasswordReset))
    token = reset_token(pending.id)
    assert pending.token_hash == token_digest(token)
    assert token not in responses[0].text
    for invalid in ("bad", str(uuid4()) + ".bad", token[:-1] + ("a" if token[-1] != "a" else "b")):
        assert (
            await client.post(
                "/api/auth/password/reset", json={"token": invalid, "new_password": NEW_PASSWORD}
            )
        ).status_code == 401
    assert (
        await client.post(
            "/api/auth/password/reset", json={"token": token, "new_password": "password1234"}
        )
    ).status_code == 422
    response = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert (
        await client.post(
            "/api/auth/password/reset", json={"token": token, "new_password": PASSWORD}
        )
    ).status_code == 401
    for login in (first, second):
        assert (await client.get("/api/organizations", headers=bearer(login))).status_code == 401
    assert (await use_refresh(client, cookie)).status_code == 401
    await sign_in(client, password=NEW_PASSWORD)


async def test_expired_reset_and_mail_retry(client, db_session, caplog):
    await account(client)
    await client.post("/api/auth/password/reset-request", json={"email": "session@example.com"})
    pending = await db_session.scalar(select(PasswordReset))
    token = reset_token(pending.id)
    with patch("app.services.reset_mail.send_reset", side_effect=OSError("private SMTP data")):
        assert await ResetMailService(db_session).process_one()
    assert pending.attempts == 1 and pending.sent_at is None
    pending.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    with patch("app.services.reset_mail.send_message") as send:
        assert await ResetMailService(db_session).process_one()
        text = send.call_args.args[0].get_content()
        assert "#reset=" + token in text
    pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    response = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 401
    assert token not in caplog.text and "private SMTP data" not in caplog.text


async def test_self_deactivation_is_disabled_and_preserves_sessions(client, db_session):
    response = await account(client)
    cookie = client.cookies.get(REFRESH_COOKIE)
    for password in ("wrong", PASSWORD):
        result = await client.post(
            "/api/auth/deactivate", headers=bearer(response), json={"current_password": password}
        )
        assert result.status_code == 403
    user = await db_session.scalar(select(User))
    assert user.is_active
    assert (await client.get("/api/organizations", headers=bearer(response))).status_code == 200
    assert (await use_refresh(client, cookie)).status_code == 200


@pytest.mark.parametrize(
    "key",
    [
        "short",
        "x" * 100,
        "0123456789abcdef" * 4,
        "development-secret-key-change-in-production-0123456789",
        "replace-with-a-random-secret-at-least-32-characters",
    ],
)
def test_weak_keys_rejected_without_disclosure(key):
    with pytest.raises(ValidationError) as error:
        Settings(database_url="sqlite+aiosqlite://", auth_secret_key=key)
    assert key not in str(error.value)


def test_random_key_accepted():
    Settings(database_url="sqlite+aiosqlite://", auth_secret_key=secrets.token_urlsafe(48))


async def test_ownership_transfer_routes_are_removed(client):
    response = await account(client)
    for scope in ("organizations", "projects"):
        result = await client.post(
            f"/api/{scope}/{uuid4()}/transfer-ownership",
            headers=bearer(response),
            json={"email": "successor@example.com"},
        )
        assert result.status_code == 404
