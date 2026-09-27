from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def test_register_returns_public_user_data(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": " User@example.com ", "password": "correct horse battery staple"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_rejects_duplicate_email_case_insensitively(
    client: AsyncClient, user_ids: tuple[UUID, UUID]
) -> None:
    first = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )
    second = await client.post(
        "/api/auth/register",
        json={"email": "USER@EXAMPLE.COM", "password": "correct horse battery staple"},
    )

    assert first.status_code == 201
    assert second.status_code == 409


async def test_register_validates_email_and_password(client: AsyncClient) -> None:
    short_password = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    long_password = await client.post(
        "/api/auth/register",
        json={"email": "long@example.com", "password": "p" * 129},
    )
    invalid_email = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "correct horse battery staple"},
    )

    assert short_password.status_code == 422
    assert long_password.status_code == 422
    assert invalid_email.status_code == 422


async def test_password_hash_is_not_plaintext(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    password = "correct horse battery staple"
    response = await client.post(
        "/api/auth/register",
        json={"email": "hash@example.com", "password": password},
    )

    assert response.status_code == 201
    user = await db_session.scalar(select(User).where(User.email == "hash@example.com"))
    assert user is not None
    assert user.password_hash != password
    assert user.password_hash.startswith("$argon2")


async def test_login_returns_token_and_rejects_invalid_credentials(
    client: AsyncClient,
) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "login@example.com", "password": "correct horse battery staple"},
    )

    success = await client.post(
        "/api/auth/login",
        json={"email": "LOGIN@example.com", "password": "correct horse battery staple"},
    )
    invalid = await client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "wrong password"},
    )
    unknown = await client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "wrong password"},
    )

    assert success.status_code == 200
    assert success.json()["token_type"] == "bearer"
    assert success.json()["user"]["email"] == "login@example.com"
    assert invalid.status_code == 401
    assert unknown.status_code == 401
    assert invalid.json() == unknown.json()


async def test_inactive_user_cannot_login(client: AsyncClient, db_session: AsyncSession) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "inactive@example.com", "password": "correct horse battery staple"},
    )
    user = await db_session.scalar(select(User).where(User.email == "inactive@example.com"))
    assert user is not None
    user.is_active = False
    await db_session.commit()

    response = await client.post(
        "/api/auth/login",
        json={"email": "inactive@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 401


async def test_invalid_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/organizations", headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401
