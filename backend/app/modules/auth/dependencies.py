from collections.abc import AsyncIterator, Awaitable
from typing import Annotated, cast

from fastapi import Depends, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.modules.auth.errors import AuthError
from app.modules.auth.security import digest

LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


def config(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def database(request: Request) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(request.app.state.engine, expire_on_commit=False)
    async with factory() as session:
        yield session


Database = Annotated[AsyncSession, Depends(database)]


async def limit(request: Request, bucket: str, identity: str, maximum: int, seconds: int) -> None:
    client: Redis | None = request.app.state.redis
    if client is None:
        raise AuthError(503, "AUTH_UNAVAILABLE", "Authentication is temporarily unavailable.")
    key = f"{config(request).rate_limit_prefix}:{bucket}:{digest(identity)}"
    try:
        count = await cast(Awaitable[int], client.eval(LIMIT_SCRIPT, 1, key, seconds))
    except RedisError, OSError:
        raise AuthError(
            503, "AUTH_UNAVAILABLE", "Authentication is temporarily unavailable."
        ) from None
    if int(count) > maximum:
        raise AuthError(429, "RATE_LIMITED", "Too many attempts. Please try again later.")


async def protect(request: Request) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if (
            request.headers.get("origin") not in config(request).trusted_origins
            or request.headers.get("x-csrf-protection") != "1"
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            raise AuthError(403, "CSRF_REJECTED", "Request origin could not be verified.")
    # Never trust user-supplied X-Forwarded-For. Only a configured trusted proxy may set client IP.
    ip = request.client.host if request.client else "unknown"
    action = request.url.path.rsplit("/", 1)[-1]
    if not request.url.path.startswith("/api/v1/auth/"):
        # Tenant UUIDs must not create separate IP buckets that bypass shared limits.
        action = "organizations"
    maximum, seconds = {
        "register": (10, 3600),
        "login": (60, 900),
        "forgot-password": (20, 3600),
        "reset-password": (30, 900),
        "verify-email": (30, 900),
    }.get(action, (120, 60))
    await limit(request, f"ip:{action}", ip, maximum, seconds)
