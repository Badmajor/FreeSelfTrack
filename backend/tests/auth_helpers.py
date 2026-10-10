from app.db.session import get_session
from app.main import app
from app.models import User, UserProfile
from app.services.auth import password_hash


async def seed_account(
    email, password="correct horse battery staple", first_name="Test", last_name="User", **flags
):
    """Seed a pre-existing account; tests of onboarding use the real administrative API."""
    generator = app.dependency_overrides[get_session]()
    session = await anext(generator)
    try:
        user = User(
            email=email.strip().casefold(),
            password_hash=password_hash.hash(password),
            profile=UserProfile(first_name=first_name, last_name=last_name),
            **flags,
        )
        session.add(user)
        await session.commit()
        return user.id
    finally:
        await generator.aclose()


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
