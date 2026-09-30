import os

import httpx
import pytest

from app.core.config import SmokeSettings
from app.main import create_app
from scripts.smoke import run_checks

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with the Compose stack running",
    ),
]


async def test_real_infrastructure_connections() -> None:
    assert await run_checks(SmokeSettings())


async def test_readiness_against_real_postgresql() -> None:
    app = create_app(SmokeSettings())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
