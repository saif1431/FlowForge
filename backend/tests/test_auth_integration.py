import asyncio
import os
from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import SmokeSettings
from app.db.models import AuditEvent, AuthSession, AuthToken, User
from app.main import create_app
from app.modules.auth.security import digest
from app.modules.auth.service import issue_token, now

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL and Redis"
    ),
]
PASSWORD = "a strong test password 123!"
HEADERS = {"Origin": "http://127.0.0.1:3000", "X-CSRF-Protection": "1"}


@pytest.fixture
async def auth_env() -> AsyncIterator[tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings]]:
    settings = SmokeSettings(rate_limit_prefix=f"flowforge:test:{uuid4().hex}")
    schema = f"test_auth_{uuid4().hex}"
    admin = create_async_engine(settings.database_url.get_secret_value(), hide_parameters=True)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        hide_parameters=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    app = create_app(settings)
    try:
        async with engine.begin() as conn:

            def migrate(connection: object) -> None:
                cfg = Config("alembic.ini")
                cfg.attributes["connection"] = connection
                command.upgrade(cfg, "head")
                command.check(cfg)

            await conn.run_sync(migrate)
        async with app.router.lifespan_context(app):
            app.state.engine = engine
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers=HEADERS,
            ) as client:
                yield client, engine, settings
            # Delete only keys belonging to this test's random namespace.
            redis = app.state.redis
            async for key in redis.scan_iter(match=f"{settings.rate_limit_prefix}:*"):
                await redis.delete(key)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def signup(client: httpx.AsyncClient, email: str = "alice@example.com") -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 202, response.text


async def signin(
    client: httpx.AsyncClient, email: str = "alice@example.com", password: str = PASSWORD
) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    return client.cookies["flowforge_session"]


async def token_for(engine: AsyncEngine, purpose: str, email: str = "alice@example.com") -> str:
    async with async_sessionmaker(engine)() as db:
        user = await db.scalar(select(User).where(User.email == email).with_for_update())
        assert user is not None
        raw = await issue_token(db, user.id, purpose, str(uuid4()))
        await db.commit()
        return raw


async def test_registration_login_and_redaction(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, engine, _ = auth_env
    await signup(client, "Alice@Example.com")
    await signup(client)
    raw = await signin(client)
    me = await client.get("/api/v1/auth/me")
    assert me.json()["email"] == "alice@example.com"
    async with async_sessionmaker(engine)() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 1
        user = await db.scalar(select(User))
        assert user is not None and user.password_hash.startswith("$argon2id$")
        assert await db.scalar(select(AuthSession.token_hash)) == digest(raw)
        actions = list(await db.scalars(select(AuditEvent.action)))
        assert "auth.register" in actions and "auth.login" in actions
    failure = await client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
    )
    assert failure.status_code == unknown.status_code == 401
    assert failure.json()["error"]["message"] == unknown.json()["error"]["message"]
    invalid = await client.post(
        "/api/v1/auth/register", json={"email": "bad", "password": "secret-sentinel"}
    )
    assert invalid.status_code == 422 and "secret-sentinel" not in invalid.text
    assert "password" not in me.text and raw not in me.text


async def test_session_ownership_logout_and_logout_all(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, _, _ = auth_env
    await signup(client)
    first = await signin(client)
    own_id = (await client.get("/api/v1/auth/sessions")).json()["items"][0]["id"]
    second = await signin(client)
    assert first != second
    assert len((await client.get("/api/v1/auth/sessions")).json()["items"]) == 2
    await signup(client, "bob@example.com")
    await signin(client, "bob@example.com")
    assert (await client.delete(f"/api/v1/auth/sessions/{own_id}")).status_code == 404
    client.cookies.set("flowforge_session", second, domain="test.local", path="/")
    assert (await client.delete(f"/api/v1/auth/sessions/{own_id}")).status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers={"Cookie": f"flowforge_session={first}"})
    ).status_code == 401
    assert (await client.post("/api/v1/auth/logout-all")).status_code == 204
    assert (
        await client.get("/api/v1/auth/me", headers={"Cookie": f"flowforge_session={second}"})
    ).status_code == 401
    await signin(client)
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


@pytest.mark.parametrize("expired_field", ["expires_at", "last_seen_at"])
async def test_expired_sessions(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings], expired_field: str
) -> None:
    client, engine, _ = auth_env
    await signup(client)
    await signin(client)
    async with engine.begin() as conn:
        await conn.execute(update(AuthSession).values({expired_field: now() - timedelta(days=8)}))
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_verify_email_single_use_concurrency(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, engine, _ = auth_env
    await signup(client)
    await signin(client)
    raw = await token_for(engine, "verify_email")
    replies = await asyncio.gather(
        *[client.post("/api/v1/auth/verify-email", json={"token": raw}) for _ in range(2)]
    )
    assert sorted(reply.status_code for reply in replies) == [200, 400]
    assert (await client.get("/api/v1/auth/me")).json()["email_verified_at"] is not None
    async with async_sessionmaker(engine)() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "auth.verify_email_completed")
            )
            == 1
        )


async def test_reset_password_revokes_all_sessions(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, engine, _ = auth_env
    await signup(client)
    first = await signin(client)
    second = await signin(client)
    raw = await token_for(engine, "reset_password")
    replacement = "a different long password 456!"
    replies = await asyncio.gather(
        *[
            client.post("/api/v1/auth/reset-password", json={"token": raw, "password": replacement})
            for _ in range(2)
        ]
    )
    assert sorted(reply.status_code for reply in replies) == [200, 400]
    for old in (first, second):
        assert (
            await client.get("/api/v1/auth/me", headers={"Cookie": f"flowforge_session={old}"})
        ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
        )
    ).status_code == 401
    await signin(client, password=replacement)


async def test_token_expiry_superseding_and_purpose(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, engine, _ = auth_env
    await signup(client)
    old = await token_for(engine, "verify_email")
    fresh = await token_for(engine, "verify_email")
    assert (await client.post("/api/v1/auth/verify-email", json={"token": old})).status_code == 400
    assert (
        await client.post(
            "/api/v1/auth/reset-password", json={"token": fresh, "password": PASSWORD}
        )
    ).status_code == 400
    async with engine.begin() as conn:
        await conn.execute(update(AuthToken).values(expires_at=now() - timedelta(seconds=1)))
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": fresh})
    ).status_code == 400


async def test_csrf_cors_and_no_token_disclosure(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, _, _ = auth_env
    for headers in (
        {"Origin": "https://evil.example"},
        {"X-CSRF-Protection": ""},
        {"Sec-Fetch-Site": "cross-site"},
    ):
        assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 403
    preflight = await client.options(
        "/api/v1/auth/login",
        headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-protection",
        },
    )
    assert preflight.headers["access-control-allow-origin"] == HEADERS["Origin"]
    evil = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in evil.headers
    await signup(client)
    a = await client.post("/api/v1/auth/forgot-password", json={"email": "alice@example.com"})
    b = await client.post("/api/v1/auth/forgot-password", json={"email": "absent@example.com"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert "token" not in a.text


async def test_redis_rate_limit_and_outage(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, _, settings = auth_env
    for _ in range(3):
        assert (
            await client.post("/api/v1/auth/forgot-password", json={"email": "absent@example.com"})
        ).status_code == 202
    assert (
        await client.post("/api/v1/auth/forgot-password", json={"email": "absent@example.com"})
    ).status_code == 429
    # Separate app instance uses the same real Redis counters.
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=HEADERS
        ) as other:
            assert (
                await other.post(
                    "/api/v1/auth/forgot-password", json={"email": "absent@example.com"}
                )
            ).status_code == 429
            from unittest.mock import AsyncMock, patch

            from redis.exceptions import ConnectionError as RedisConnectionError

            with patch.object(
                app.state.redis,
                "eval",
                AsyncMock(side_effect=RedisConnectionError("secret-sentinel")),
            ):
                response = await other.post("/api/v1/auth/logout")
                assert response.status_code == 503 and "secret-sentinel" not in response.text


async def test_concurrent_registration(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, engine, _ = auth_env
    replies = await asyncio.gather(
        *[
            client.post(
                "/api/v1/auth/register", json={"email": "same@example.com", "password": PASSWORD}
            )
            for _ in range(2)
        ]
    )
    assert all(reply.status_code == 202 for reply in replies)
    async with async_sessionmaker(engine)() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 1


async def test_migration_round_trip(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    _, engine, _ = auth_env
    async with engine.begin() as conn:

        def round_trip(connection: object) -> None:
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = connection
            command.downgrade(cfg, "base")
            command.upgrade(cfg, "head")
            command.check(cfg)

        await conn.run_sync(round_trip)


async def test_secure_cookie_in_production(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, engine, settings = auth_env
    await signup(client)
    secure_settings = settings.model_copy(
        update={"app_env": "production", "trusted_origins": ["https://app.example.com"]}
    )
    app = create_app(secure_settings)
    async with app.router.lifespan_context(app):
        app.state.engine = engine
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://test",
            headers={"Origin": "https://app.example.com", "X-CSRF-Protection": "1"},
        ) as secure_client:
            response = await secure_client.post(
                "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
            )
            assert response.status_code == 200
            cookie = response.headers["set-cookie"]
            assert "__Host-flowforge_session=" in cookie
            assert "Secure" in cookie and "HttpOnly" in cookie and "Path=/" in cookie
            assert "Domain=" not in cookie
            assert (await secure_client.get("/api/v1/auth/me")).status_code == 200


async def test_reset_serializes_with_login(
    auth_env: tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings],
) -> None:
    client, engine, _ = auth_env
    await signup(client)
    raw = await token_for(engine, "reset_password")
    login, reset = await asyncio.gather(
        client.post(
            "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
        ),
        client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "password": "a new safe password 456!"},
        ),
    )
    assert reset.status_code == 200 and login.status_code in {200, 401}
    if login.status_code == 200:
        old = login.cookies["flowforge_session"]
        assert (
            await client.get("/api/v1/auth/me", headers={"Cookie": f"flowforge_session={old}"})
        ).status_code == 401
