from auth_helpers import confirm_registration
from httpx import AsyncClient


async def test_registration_requires_and_returns_profile(client: AsyncClient) -> None:
    missing_names = await client.post(
        "/api/auth/register",
        json={"email": "profile@example.com", "password": "correct horse battery staple"},
    )
    assert missing_names.status_code == 422

    registered = await client.post(
        "/api/auth/register",
        json={
            "email": "profile@example.com",
            "password": "correct horse battery staple",
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
    )
    assert registered.status_code == 202
    await confirm_registration(client, "profile@example.com")

    token = (
        await client.post(
            "/api/auth/login",
            json={"email": "profile@example.com", "password": "correct horse battery staple"},
        )
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile = await client.get("/api/users/me/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["last_name"] == "Lovelace"

    updated = await client.patch(
        "/api/users/me/profile",
        json={"first_name": "Grace", "last_name": "Hopper"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["first_name"] == "Grace"
