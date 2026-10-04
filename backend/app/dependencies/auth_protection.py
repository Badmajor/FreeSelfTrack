from collections.abc import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.auth_protection import AuthLimiter, client_address


async def auth_limiter() -> AsyncIterator[AuthLimiter]:
    async with Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True
    ) as redis:
        yield AuthLimiter(redis)


def auth_client_address(request: Request) -> str:
    return client_address(
        request.client.host if request.client else "unknown", request.headers.get("x-forwarded-for")
    )
