import io
import os
import secrets
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from urllib3.response import HTTPResponse

os.environ.setdefault("TRACKER_TRUSTED_HOSTS", '["test", "testserver", "localhost", "127.0.0.1"]')
os.environ.setdefault("ADMIN_EMAIL", "test-bootstrap")
os.environ.setdefault("ADMIN_PASSWORD", "test-bootstrap-only")
os.environ.setdefault("TRACKER_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TRACKER_AUTH_SECRET_KEY", secrets.token_urlsafe(48))

from app.core.object_storage import ObjectStorage, StorageUnavailable  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.dependencies.auth_protection import auth_limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.services.auth_protection import AuthLimiter  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    app.dependency_overrides[auth_limiter] = lambda: AuthLimiter(redis)
    app.dependency_overrides[get_session] = test_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        headers={"Origin": "http://localhost:5173", "X-CSRF-Protection": "1"},
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    await redis.aclose()
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(client: AsyncClient) -> AsyncIterator[AsyncSession]:
    session_generator = app.dependency_overrides[get_session]()
    session = await anext(session_generator)
    try:
        yield session
    finally:
        await session_generator.aclose()


@pytest_asyncio.fixture
async def user_ids() -> tuple[UUID, UUID]:
    return uuid4(), uuid4()


class MemoryStorage(ObjectStorage):
    """Test double only; production always uses the configured private S3 service."""

    def __init__(self):
        self.objects = {}
        self.opens = 0

    def put(self, key, stream, size):
        stream.seek(0)
        self.objects[key] = stream.read(size)

    def open(self, key):
        self.opens += 1
        if key not in self.objects:
            raise StorageUnavailable()
        return HTTPResponse(body=io.BytesIO(self.objects[key]), preload_content=False)

    def abort_abandoned_parts(self):
        return 0

    def keys(self):
        return iter(list(self.objects))

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture(autouse=True)
def attachment_storage(monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("app.services.chat.get_storage", lambda: storage)
    monkeypatch.setattr("app.api.chat.get_storage", lambda: storage)
    return storage
