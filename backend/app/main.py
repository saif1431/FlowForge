from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from redis.asyncio import Redis

from app.api.health import router as health_router
from app.api.middleware import AuthBoundary, auth_error, validation_error
from app.core.config import Settings, load_settings
from app.db.connection import create_engine
from app.modules.auth.errors import AuthError
from app.modules.auth.router import router as auth_router
from app.modules.organizations.router import router as organizations_router
from app.modules.roles.router import router as roles_router
from app.modules.teams.router import router as teams_router
from app.modules.workflows.router import router as workflows_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings if settings is not None else load_settings()
        engine = create_engine(config)
        app.state.settings = config
        app.state.engine = engine
        redis = (
            Redis.from_url(
                config.redis_url.get_secret_value(),
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            if config.redis_url
            else None
        )
        app.state.redis = redis
        try:
            yield
        finally:
            if redis is not None:
                await redis.aclose()
            await engine.dispose()

    app = FastAPI(title="FlowForge API", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(organizations_router)
    app.include_router(roles_router)
    app.include_router(teams_router)
    app.include_router(workflows_router)
    app.add_middleware(AuthBoundary)
    app.add_exception_handler(AuthError, auth_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error)  # type: ignore[arg-type]
    return app


app = create_app()
