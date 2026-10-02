from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.health import database_probe
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


async def test_liveness_does_not_require_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("failure", [None, RuntimeError("password=do-not-expose"), TimeoutError()])
async def test_readiness_response(settings: Settings, failure: Exception | None) -> None:
    app = create_app(settings)

    async def probe() -> None:
        if failure is not None:
            raise failure

    app.dependency_overrides[database_probe] = lambda: probe
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health/ready")
    assert response.status_code == (503 if failure else 200)
    assert response.json() == {"status": "unavailable" if failure else "ready"}
    assert response.headers["cache-control"] == "no-store"
    assert "do-not-expose" not in response.text


async def test_unreachable_database_returns_503(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


async def test_readiness_requires_redis_but_liveness_does_not(settings: Settings) -> None:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.redis = SimpleNamespace(ping=AsyncMock(side_effect=OSError("secret-sentinel")))
        with patch("app.api.health.ping_database", AsyncMock()):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                ready = await client.get("/health/ready")
                assert ready.status_code == 503 and "secret-sentinel" not in ready.text
                assert (await client.get("/health/live")).status_code == 200
