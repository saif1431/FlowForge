from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, load_settings


def test_missing_database_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="Invalid configuration fields: database_url"):
        load_settings()


def test_invalid_secret_is_not_exposed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "mysql://user:sensitive-value@localhost/database")
    with pytest.raises(RuntimeError) as error:
        load_settings()
    assert "sensitive-value" not in str(error.value)
    assert error.value.__suppress_context__


def test_settings_representation_hides_database_secret(settings: Settings) -> None:
    assert settings.database_url.get_secret_value() not in repr(settings)


@pytest.mark.parametrize("timeout", [0, -1, 11])
def test_timeout_must_be_bounded(settings: Settings, timeout: float) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({**settings.model_dump(), "dependency_timeout_seconds": timeout})


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_cannot_disable_email_verification(
    settings: Settings, environment: str
) -> None:
    with pytest.raises(ValidationError, match="Email verification is required"):
        Settings.model_validate(
            {**settings.model_dump(), "app_env": environment, "require_email_verification": False}
        )
