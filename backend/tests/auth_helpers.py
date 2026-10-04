from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session
from app.main import app
from app.models.registration import PendingRegistration
from app.services.verification import create_verification_token


async def confirmation_token(email: str) -> str:
    generator = app.dependency_overrides[get_session]()
    session = await anext(generator)
    try:
        registration = await session.scalar(
            select(PendingRegistration)
            .where(PendingRegistration.email == email.strip().casefold())
            .order_by(PendingRegistration.expires_at.desc())
        )
        assert registration is not None
        return create_verification_token(registration)
    finally:
        await generator.aclose()


async def confirm_registration(
    client: AsyncClient, email: str, password: str = "correct horse battery staple"
) -> None:
    response = await client.post(
        "/api/auth/verify-email",
        json={
            "token": await confirmation_token(email),
            "password": password,
        },
    )
    assert response.status_code == 200, response.text
