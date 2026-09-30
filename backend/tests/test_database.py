import asyncio
from unittest.mock import MagicMock

import pytest

from app.db.connection import ping_database


async def test_database_probe_has_overall_deadline() -> None:
    class StalledConnection:
        async def __aenter__(self) -> None:
            await asyncio.Event().wait()

        async def __aexit__(self, *args: object) -> None:
            pass

    engine = MagicMock()
    engine.connect.return_value = StalledConnection()
    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(ping_database(engine, 0.01), timeout=1)
    # The probe's own deadline must fire, rather than the outer test safety timeout.
    assert asyncio.get_running_loop().time() - started < 0.5
