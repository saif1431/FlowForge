from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "test", "staging", "production"] = "local"
    database_url: SecretStr
    dependency_timeout_seconds: float = Field(default=3, gt=0, le=10)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
            valid = url.drivername == "postgresql+asyncpg" and bool(
                url.host and url.database and url.username and url.password
            )
        except Exception:
            valid = False
        if not valid:
            raise ValueError(
                "Expected a PostgreSQL asyncpg URL with host, database and credentials"
            )
        return value


class SmokeSettings(Settings):
    redis_url: SecretStr
    rabbitmq_url: SecretStr
    minio_endpoint: AnyHttpUrl


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        fields = sorted({str(error["loc"][0]) for error in exc.errors()})
        raise RuntimeError(f"Invalid configuration fields: {', '.join(fields)}") from None
