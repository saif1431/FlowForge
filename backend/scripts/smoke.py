"""Read-only connection checks. Run from backend: uv run python -m scripts.smoke."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

import httpx
import psycopg
from celery import Celery
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.engine import make_url

from app.core.config import SmokeSettings
from app.db.connection import create_engine, ping_database


async def postgres_check(settings: SmokeSettings) -> None:
    engine = create_engine(settings)
    try:
        await ping_database(engine, settings.dependency_timeout_seconds)
    finally:
        await engine.dispose()


def postgres_sync_check(settings: SmokeSettings) -> None:
    url = make_url(settings.database_url.get_secret_value())
    with psycopg.connect(
        host=url.host,
        port=url.port or 5432,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=int(settings.dependency_timeout_seconds) + 1,
        options="-c statement_timeout=3000",
    ) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)


async def redis_check(settings: SmokeSettings) -> None:
    async with Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=settings.dependency_timeout_seconds,
        socket_timeout=settings.dependency_timeout_seconds,
    ) as client:
        # redis-py shares this command annotation with its synchronous client.
        await cast(Awaitable[bool], client.ping())


def rabbitmq_check(settings: SmokeSettings) -> None:
    with Celery("flowforge-smoke", broker=settings.rabbitmq_url.get_secret_value()) as app:
        with app.connection_for_read(connect_timeout=settings.dependency_timeout_seconds) as conn:
            conn.ensure_connection(max_retries=0)


async def minio_check(settings: SmokeSettings) -> None:
    async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
        response = await client.get(
            f"{str(settings.minio_endpoint).rstrip('/')}/minio/health/ready"
        )
        response.raise_for_status()


async def run_checks(settings: SmokeSettings) -> bool:
    checks: list[tuple[str, Callable[[], Awaitable[None]]]] = [
        ("postgresql-async", lambda: postgres_check(settings)),
        ("postgresql-sync", lambda: asyncio.to_thread(postgres_sync_check, settings)),
        ("redis", lambda: redis_check(settings)),
        ("rabbitmq", lambda: asyncio.to_thread(rabbitmq_check, settings)),
        ("minio", lambda: minio_check(settings)),
    ]
    passed = True
    for name, check in checks:
        try:
            async with asyncio.timeout(settings.dependency_timeout_seconds + 2):
                await check()
        except Exception:
            print(f"FAIL {name} (check configuration and service health)")
            passed = False
        else:
            print(f"PASS {name}")
    return passed


if __name__ == "__main__":
    try:
        settings = SmokeSettings()
    except ValidationError:
        raise SystemExit("Invalid smoke-check configuration; check backend/.env.") from None
    raise SystemExit(0 if asyncio.run(run_checks(settings)) else 1)
