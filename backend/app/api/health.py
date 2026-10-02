import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.db.connection import ping_database

router = APIRouter(prefix="/health", tags=["health"])
DatabaseProbe = Callable[[], Awaitable[None]]


class HealthResponse(BaseModel):
    status: Literal["alive", "ready", "unavailable"]


def database_probe(request: Request) -> DatabaseProbe:
    async def probe() -> None:
        timeout = request.app.state.settings.dependency_timeout_seconds
        async with asyncio.timeout(timeout):
            await ping_database(request.app.state.engine, timeout)
            redis = request.app.state.redis
            if redis is None:
                raise RuntimeError("Authentication rate limiter is not configured")
            await cast(Awaitable[bool], redis.ping())

    return probe


@router.get("/live", response_model=HealthResponse)
async def live(response: Response) -> HealthResponse:
    response.headers["Cache-Control"] = "no-store"
    return HealthResponse(status="alive")


@router.get("/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def ready(
    response: Response, probe: Annotated[DatabaseProbe, Depends(database_probe)]
) -> HealthResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        await probe()
    except Exception:
        # Health endpoints deliberately reveal neither connection details nor exceptions.
        response.status_code = 503
        return HealthResponse(status="unavailable")
    return HealthResponse(status="ready")
