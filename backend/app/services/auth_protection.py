import hashlib
import hmac
import ipaddress
import logging
from collections.abc import Awaitable
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.services.errors import DomainError

logger = logging.getLogger("security.auth")


class AuthUnavailableError(DomainError):
    status_code = 503


class PasswordPolicyError(DomainError):
    status_code = 422


class ThrottledError(DomainError):
    status_code = 429

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many attempts. Try again later.")
        self.headers = {"Retry-After": str(retry_after)}


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def normalize_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    return address.compressed


def client_address(peer: str, forwarded: str | None) -> str:
    address = normalize_address(peer)
    networks = [ipaddress.ip_network(n) for n in get_settings().trusted_proxy_networks]

    def trusted(value: str) -> bool:
        return value != "unknown" and any(ipaddress.ip_address(value) in n for n in networks)

    # Walk from the socket toward the client, discarding only explicitly trusted hops.
    if forwarded and trusted(address):
        for hop in reversed(forwarded.split(",")):
            if not trusted(address):
                break
            address = normalize_address(hop.strip())
    return address


# Both budgets are reserved atomically, before any password hashing or DB work.
# Rejected attempts neither extend the fixed window nor consume the other budget.
LIMIT_SCRIPT = """
local retry = 0
for i, key in ipairs(KEYS) do
    local count = tonumber(redis.call('GET', key) or '0')
    if count >= tonumber(ARGV[i]) then
        local ttl = redis.call('TTL', key)
        if ttl < 0 then ttl = tonumber(ARGV[3]) end
        retry = math.max(retry, ttl, 1)
    end
end
if retry > 0 then return retry end
for _, key in ipairs(KEYS) do
    local count = redis.call('INCR', key)
    if count == 1 then redis.call('EXPIRE', key, ARGV[3]) end
end
return 0
"""


class AuthLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def check(
        self, operation: Literal["login", "register", "verify"], identifier: str, address: str
    ) -> None:
        settings = get_settings()

        def digest(value: str) -> str:
            return hmac.new(
                settings.auth_secret_key.encode(), value.encode(), hashlib.sha256
            ).hexdigest()

        # One hash slot permits atomic execution on Redis Cluster too.
        keys = [
            f"auth:{{limits}}:{operation}:account:{digest(identifier)}",
            f"auth:{{limits}}:{operation}:address:{digest(normalize_address(address))}",
        ]
        try:
            # redis-py shares EVAL stubs between sync and async clients.
            result = self.redis.eval(
                LIMIT_SCRIPT,
                2,
                *keys,
                str(getattr(settings, f"{operation}_account_limit")),
                str(getattr(settings, f"{operation}_address_limit")),
                str(settings.auth_window_seconds),
            )
            retry = int(await cast(Awaitable[int], result))
        except RedisError as exc:
            logger.warning("auth outcome=limiter_unavailable operation=%s", operation)
            raise AuthUnavailableError("Authentication temporarily unavailable") from exc
        if retry:
            logger.info("auth outcome=throttled operation=%s", operation)
            raise ThrottledError(retry)


@lru_cache
def password_blocklist(filename: str | None) -> frozenset[str]:
    # Offline baseline; deployments can add a locally maintained SHA-256 corpus.
    common = (
        "password1234",
        "password12345",
        "password123456",
        "123456789012",
        "1234567890123",
        "12345678901234",
        "123456789012345",
        "1234567890123456",
        "qwertyuiop12",
        "qwertyuiop123",
        "qwertyuiop123456",
        "abcdefghijkl",
        "admin12345678",
        "letmein123456",
        "iloveyou12345",
        "welcome12345!",
        "changeme12345",
        "passwordpassword",
        "password123!",
        "Password123!",
        "Password1234",
        "Password12345",
        "Password123456",
        "welcome123456",
    )
    hashes = {hashlib.sha256(p.encode()).hexdigest() for p in common}
    if filename:
        lines = Path(filename).read_text(encoding="ascii").splitlines()
        if not lines:
            raise ValueError("Empty offline password corpus")
        for line in lines:
            value = line.strip().lower()
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("Invalid offline password corpus")
            hashes.add(value)
    return frozenset(hashes)


async def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128 or not password.strip():
        logger.info("auth outcome=password_policy_rejected")
        raise PasswordPolicyError("Password must contain 12 to 128 characters and not be blank")
    try:
        blocked = await run_in_threadpool(password_blocklist, get_settings().breached_password_file)
    except (OSError, ValueError) as exc:
        logger.error("auth outcome=password_corpus_unavailable")
        raise AuthUnavailableError("Registration temporarily unavailable") from exc
    if hashlib.sha256(password.encode()).hexdigest() in blocked:
        logger.info("auth outcome=password_policy_rejected")
        raise PasswordPolicyError("This password is compromised or commonly used")
