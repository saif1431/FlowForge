from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import Settings, load_settings
from app.db.connection import create_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings if settings is not None else load_settings()
        engine = create_engine(config)
        app.state.settings = config
        app.state.engine = engine
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="FlowForge API", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
