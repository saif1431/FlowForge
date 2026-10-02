"""Local browser-test server with an isolated, disposable PostgreSQL schema."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import SmokeSettings
from app.main import create_app
from app.modules.auth.dependencies import Database
from app.modules.auth.service import authenticate, consume_token, issue_token

settings = SmokeSettings(
    app_env="test",
    trusted_origins=["http://127.0.0.1:3100"],
    rate_limit_prefix=f"flowforge:e2e:{uuid4().hex}",
)
app = create_app(settings)
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    schema = f"test_e2e_{uuid4().hex}"
    admin = create_async_engine(settings.database_url.get_secret_value(), hide_parameters=True)
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        hide_parameters=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.begin() as conn:

            def migrate(connection: Connection) -> None:
                cfg = Config("alembic.ini")
                cfg.attributes["connection"] = connection
                command.upgrade(cfg, "head")

            await conn.run_sync(migrate)
        async with original_lifespan(application):
            application.state.engine = engine
            yield
            async for key in application.state.redis.scan_iter(
                match=f"{settings.rate_limit_prefix}:*"
            ):
                await application.state.redis.delete(key)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


app.router.lifespan_context = lifespan

server = uvicorn.Server(
    uvicorn.Config(app, host="127.0.0.1", port=8100, access_log=False, proxy_headers=False)
)


@app.post("/__test__/shutdown", status_code=204)
async def shutdown() -> None:
    # Only this loopback-only test harness exposes the endpoint, never app.main.
    server.should_exit = True


@app.post("/__test__/verify-email", status_code=204)
async def verify_test_email(request: Request, db: Database) -> None:
    # Only the disposable browser harness bypasses delivery; never installed in app.main.
    user, _ = await authenticate(db, request.cookies.get(settings.session_cookie), settings)
    token = await issue_token(db, user.id, "verify_email", str(uuid4()))
    await db.commit()
    await consume_token(db, token, "verify_email", str(uuid4()))


if __name__ == "__main__":
    # The harness never binds to a public interface and never trusts forwarded headers.
    asyncio.run(server.serve())
