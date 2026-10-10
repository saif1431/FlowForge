from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "test", "staging", "production"] = "local"
    database_url: SecretStr
    dependency_timeout_seconds: float = Field(default=3, gt=0, le=10)
    redis_url: SecretStr | None = None
    trusted_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    session_absolute_seconds: int = Field(default=604800, ge=60, le=2592000)
    session_idle_seconds: int = Field(default=86400, ge=60, le=604800)
    rate_limit_prefix: str = "flowforge:auth"
    require_email_verification: bool = True

    @field_validator("trusted_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        from urllib.parse import urlsplit

        if not origins:
            raise ValueError("At least one trusted frontend origin is required")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in origin
            ):
                raise ValueError("Expected exact HTTP(S) origins without paths or credentials")
        return origins

    @model_validator(mode="after")
    def production_auth(self) -> Settings:
        if self.app_env in {"staging", "production"}:
            if not self.require_email_verification:
                raise ValueError("Email verification is required outside local/test environments")
            if self.redis_url is None or any(
                not origin.startswith("https://") for origin in self.trusted_origins
            ):
                raise ValueError("Production authentication requires Redis and HTTPS origins")
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.app_env in {"staging", "production"}

    @property
    def session_cookie(self) -> str:
        return "__Host-flowforge_session" if self.secure_cookies else "flowforge_session"

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
