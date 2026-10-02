import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.modules.auth.schemas import RegisterInput
from app.modules.auth.security import digest, hash_password, new_token, verify_password


async def test_argon2_and_random_session_material() -> None:
    password = "a sufficiently long password"
    encoded = await hash_password(password)
    assert encoded.startswith("$argon2id$")
    assert await verify_password(password, encoded)
    assert not await verify_password("incorrect", encoded)
    first, second = new_token(), new_token()
    assert len(first) == 43 and first != second
    assert len(digest(first)) == 64 and first not in digest(first)


def test_email_normalization_and_password_bounds() -> None:
    body = RegisterInput(email="Person@Example.com", password="a long password indeed")
    assert body.email == "person@example.com"
    assert "a long password" not in repr(body)
    for password in ("short", "x" * 129):
        with pytest.raises(ValidationError):
            RegisterInput(email="person@example.com", password=password)


def test_production_cookie_and_origin_configuration(settings: Settings) -> None:
    values = settings.model_dump()
    values.update(app_env="production", trusted_origins=["https://flowforge.example"])
    from pydantic import SecretStr

    values["redis_url"] = SecretStr("redis://127.0.0.1:6379/0")
    secure = Settings(_env_file=None, **values)
    assert secure.secure_cookies
    assert secure.session_cookie == "__Host-flowforge_session"
    for origin in ("*", "http://flowforge.example", "https://flowforge.example/path"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{**values, "trusted_origins": [origin]})


async def test_csrf_precedes_database_and_redis(settings: Settings) -> None:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/auth/logout")
            assert response.status_code == 403
            response = await client.post(
                "/api/v1/auth/logout",
                headers={"Origin": settings.trusted_origins[0], "X-CSRF-Protection": "1"},
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "AUTH_UNAVAILABLE"
            large = await client.post("/api/v1/auth/login", content=b"x" * 16385)
            assert large.status_code == 413
