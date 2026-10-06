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


def authenticated_id(headers):
    from app.services.sessions import read_access_token

    return read_access_token(headers["Authorization"].removeprefix("Bearer "))[0]


async def set_system_admin(headers, enabled=True):
    from app.models import User

    generator = app.dependency_overrides[get_session]()
    session = await anext(generator)
    try:
        user = await session.get(User, authenticated_id(headers))
        user.is_system_admin = enabled
        await session.commit()
    finally:
        await generator.aclose()


async def seed_manager(headers, scope, identifier):
    """Explicit fixture participation, independent from resource creation semantics."""
    from uuid import UUID

    from app.models import OrganizationMember, ProjectMember

    generator = app.dependency_overrides[get_session]()
    session = await anext(generator)
    try:
        model = OrganizationMember if scope == "organization" else ProjectMember
        session.add(
            model(
                **{scope + "_id": UUID(identifier)},
                user_id=authenticated_id(headers),
                role="manager",
                state="active",
            )
        )
        await session.commit()
    finally:
        await generator.aclose()
