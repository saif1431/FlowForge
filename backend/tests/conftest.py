import pytest
from pydantic import SecretStr

from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr("postgresql+asyncpg://test:test@127.0.0.1:1/test"),
        dependency_timeout_seconds=0.1,
    )
