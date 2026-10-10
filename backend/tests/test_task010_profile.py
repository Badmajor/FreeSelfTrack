from auth_helpers import seed_account
from httpx import AsyncClient


async def test_existing_account_profile_read_and_update(client: AsyncClient) -> None:
    await seed_account("profile@example.com", first_name="Ada", last_name="Lovelace")

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
