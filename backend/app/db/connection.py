import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    timeout = settings.dependency_timeout_seconds
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
        pool_timeout=timeout,
        connect_args={"timeout": timeout, "command_timeout": timeout},
    )


async def ping_database(engine: AsyncEngine, deadline_seconds: float) -> None:
    async with asyncio.timeout(deadline_seconds):
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
