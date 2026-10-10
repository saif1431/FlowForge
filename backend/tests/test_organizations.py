import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_auth_integration import pytestmark, signin, signup, token_for  # noqa: F401

from app.core.config import SmokeSettings
from app.db.models import AuditEvent, Invitation, Membership
from app.modules.auth.service import now

Env = tuple[httpx.AsyncClient, AsyncEngine, SmokeSettings]


async def account(env: Env, email: str = "alice@example.com", verified: bool = True) -> str:
    client, engine, _ = env
    await signup(client, email)
    raw = await signin(client, email)
    if verified:
        token = await token_for(engine, "verify_email", email)
        assert (
            await client.post("/api/v1/auth/verify-email", json={"token": token})
        ).status_code == 200
    return raw


async def organization(client: httpx.AsyncClient, name: str = "Org A") -> str:
    response = await client.post("/api/v1/organizations", json={"name": name})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def cookie(raw: str) -> dict[str, str]:
    return {"Cookie": f"flowforge_session={raw}"}


async def invitation(
    client: httpx.AsyncClient, org: str, email: str = "bob@example.com", raw: str | None = None
) -> str:
    response = await client.post(
        f"/api/v1/organizations/{org}/invitations",
        json={"email": email},
        headers=cookie(raw) if raw else {},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_organizations_require_verified_identity_and_csrf(auth_env: Env) -> None:
    client, _, _ = auth_env
    assert (await client.get("/api/v1/organizations")).status_code == 401
    await account(auth_env, verified=False)
    assert (await client.post("/api/v1/organizations", json={"name": "Org"})).status_code == 403
    assert (await client.get("/api/v1/invitations")).status_code == 403
    token = await token_for(auth_env[1], "verify_email")
    await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert (
        await client.post(
            "/api/v1/organizations",
            json={"name": "Org"},
            headers={"Origin": "https://evil.example"},
        )
    ).status_code == 403
    for name in ("", "   ", "x" * 121):
        assert (await client.post("/api/v1/organizations", json={"name": name})).status_code == 422
    assert (
        await client.post("/api/v1/organizations", json={"name": "Org", "owner_user_id": "fake"})
    ).status_code == 422
    org = await organization(client)
    response = await client.patch(f"/api/v1/organizations/{org}", json={"name": " Renamed "})
    assert response.status_code == 200 and response.json()["name"] == "Renamed"
    assert response.headers["cache-control"] == "no-store"
    preflight = await client.options(
        f"/api/v1/organizations/{org}",
        headers={
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type,x-csrf-protection",
        },
    )
    assert preflight.status_code == 200


async def test_cross_tenant_reads_mutations_and_child_ids(auth_env: Env) -> None:
    client, _, _ = auth_env
    alice = await account(auth_env)
    a = await organization(client)
    a_member = (await client.get(f"/api/v1/organizations/{a}/members")).json()["items"][0]["id"]
    a_invite = await invitation(client, a, "guest@example.com")
    await account(auth_env, "bob@example.com")
    b = await organization(client, "Org B")
    listing = (await client.get("/api/v1/organizations")).json()["items"]
    assert [row["id"] for row in listing] == [b]
    for suffix in ("", "/members", "/invitations"):
        assert (await client.get(f"/api/v1/organizations/{a}{suffix}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/organizations/{a}", json={"name": "stolen"})
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/organizations/{a}/invitations", json={"email": "thief@example.com"}
        )
    ).status_code == 404
    for org in (a, b):
        assert (
            await client.delete(f"/api/v1/organizations/{org}/members/{a_member}")
        ).status_code == 404
        assert (
            await client.delete(f"/api/v1/organizations/{org}/invitations/{a_invite}")
        ).status_code == 404
        assert (
            await client.post(f"/api/v1/organizations/{org}/invitations/{a_invite}/renew")
        ).status_code == 404
    assert (await client.post(f"/api/v1/invitations/{a_invite}/accept")).status_code == 404
    assert (await client.get("/api/v1/invitations")).json()["items"] == []
    assert (await client.get(f"/api/v1/organizations/{a}", headers=cookie(alice))).json()[
        "name"
    ] == "Org A"


async def test_invite_accept_remove_rejoin_and_owner_invariant(auth_env: Env) -> None:
    client, engine, _ = auth_env
    alice = await account(auth_env)
    org = await organization(client)
    invite = await invitation(client, org, "Bob@Example.com")
    bob = await account(auth_env, "bob@example.com")
    inbox = (await client.get("/api/v1/invitations")).json()["items"]
    assert inbox[0]["id"] == invite and inbox[0]["email"] == "bob@example.com"
    assert (await client.post(f"/api/v1/invitations/{invite}/accept")).status_code == 200
    assert (await client.post(f"/api/v1/invitations/{invite}/accept")).status_code == 409
    assert (await client.get(f"/api/v1/organizations/{org}")).status_code == 200
    assert (
        await client.patch(f"/api/v1/organizations/{org}", json={"name": "no"})
    ).status_code == 403
    assert (await client.get(f"/api/v1/organizations/{org}/invitations")).status_code == 403
    assert (
        await client.post(
            f"/api/v1/organizations/{org}/invitations", json={"email": "guest@example.com"}
        )
    ).status_code == 403
    members = (await client.get(f"/api/v1/organizations/{org}/members")).json()["items"]
    owner_id = next(row["id"] for row in members if row["email"] == "alice@example.com")
    bob_id = next(row["id"] for row in members if row["email"] == "bob@example.com")
    assert (
        await client.delete(
            f"/api/v1/organizations/{org}/members/{owner_id}", headers=cookie(alice)
        )
    ).status_code == 409
    assert (
        await client.delete(f"/api/v1/organizations/{org}/members/{bob_id}", headers=cookie(alice))
    ).status_code == 204
    assert (await client.get(f"/api/v1/organizations/{org}")).status_code == 404
    again = await invitation(client, org, raw=alice)
    assert (
        await client.post(f"/api/v1/invitations/{again}/accept", headers=cookie(bob))
    ).status_code == 200
    assert (await client.delete(f"/api/v1/organizations/{org}/members/{bob_id}")).status_code == 204
    async with async_sessionmaker(engine)() as db:
        assert await db.scalar(select(func.count()).select_from(Membership)) == 2
        audits = list(
            await db.scalars(select(AuditEvent).where(AuditEvent.organization_id == UUID(org)))
        )
        assert {row.action for row in audits} >= {
            "organization.created",
            "invitation.created",
            "membership.joined",
            "membership.revoked",
        }
        assert all(row.resource_id is not None for row in audits)


async def test_invitation_expiry_revocation_decline_and_renewal(auth_env: Env) -> None:
    client, engine, _ = auth_env
    alice = await account(auth_env)
    org = await organization(client)
    first = await invitation(client, org)
    assert (
        await client.post(
            f"/api/v1/organizations/{org}/invitations", json={"email": "bob@example.com"}
        )
    ).status_code == 409
    renewed = await client.post(f"/api/v1/organizations/{org}/invitations/{first}/renew")
    assert renewed.status_code == 200
    await client.delete(f"/api/v1/organizations/{org}/invitations/{first}")
    second = await invitation(client, org)
    await account(auth_env, "bob@example.com")
    assert (await client.post(f"/api/v1/invitations/{first}/accept")).status_code == 409
    assert (await client.post(f"/api/v1/invitations/{second}/decline")).status_code == 200
    assert (await client.post(f"/api/v1/invitations/{second}/accept")).status_code == 409
    third = await invitation(client, org, raw=alice)
    async with engine.begin() as conn:
        await conn.execute(
            update(Invitation)
            .where(Invitation.id == UUID(third))
            .values(expires_at=now() - timedelta(seconds=1))
        )
    assert (await client.post(f"/api/v1/invitations/{third}/accept")).status_code == 409
    assert (
        next(
            row
            for row in (await client.get("/api/v1/invitations")).json()["items"]
            if row["id"] == third
        )["status"]
        == "expired"
    )
    await invitation(client, org, raw=alice)


async def test_unverified_invitee_cannot_claim_membership(auth_env: Env) -> None:
    client, _, _ = auth_env
    await account(auth_env)
    org = await organization(client)
    invite = await invitation(client, org)
    await account(auth_env, "bob@example.com", verified=False)
    assert (await client.post(f"/api/v1/invitations/{invite}/accept")).status_code == 403
    assert (await client.post(f"/api/v1/invitations/{invite}/decline")).status_code == 403


async def test_concurrent_invitation_and_acceptance(auth_env: Env) -> None:
    client, engine, _ = auth_env
    await account(auth_env)
    org = await organization(client)
    replies = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/organizations/{org}/invitations", json={"email": "bob@example.com"}
            )
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in replies) == [201, 409]
    invite = next(r.json()["id"] for r in replies if r.status_code == 201)
    await account(auth_env, "bob@example.com")
    replies = await asyncio.gather(
        *[client.post(f"/api/v1/invitations/{invite}/accept") for _ in range(2)]
    )
    assert sorted(r.status_code for r in replies) == [200, 409]
    async with async_sessionmaker(engine)() as db:
        assert await db.scalar(select(func.count()).select_from(Membership)) == 2
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "membership.joined")
            )
            == 1
        )


async def test_accept_races_with_revoke(auth_env: Env) -> None:
    client, _, _ = auth_env
    alice = await account(auth_env)
    org = await organization(client)
    invite = await invitation(client, org)
    await account(auth_env, "bob@example.com")
    accepted, revoked = await asyncio.gather(
        client.post(f"/api/v1/invitations/{invite}/accept"),
        client.delete(f"/api/v1/organizations/{org}/invitations/{invite}", headers=cookie(alice)),
    )
    assert sorted([accepted.status_code, revoked.status_code]) == [200, 409]
    assert (await client.get(f"/api/v1/organizations/{org}")).status_code == (
        200 if accepted.status_code == 200 else 404
    )


async def test_pagination_is_tenant_scoped(auth_env: Env) -> None:
    client, _, _ = auth_env
    await account(auth_env)
    a = await organization(client)
    b = await organization(client, "Org B")
    first = (await client.get("/api/v1/organizations?limit=1")).json()
    second = (
        await client.get(f"/api/v1/organizations?limit=1&cursor={first['next_cursor']}")
    ).json()
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {a, b}
    assert second["next_cursor"] is None
    one = await invitation(client, a, "one@example.com")
    two = await invitation(client, a, "two@example.com")
    await invitation(client, b, "three@example.com")
    page = (await client.get(f"/api/v1/organizations/{a}/invitations?limit=1")).json()
    next_page = (
        await client.get(
            f"/api/v1/organizations/{a}/invitations?limit=1&cursor={page['next_cursor']}"
        )
    ).json()
    assert {page["items"][0]["id"], next_page["items"][0]["id"]} == {one, two}
    assert (await client.get("/api/v1/organizations?limit=101")).status_code == 422


async def test_invitation_limits_and_redis_failure(auth_env: Env) -> None:
    from unittest.mock import AsyncMock, patch

    from redis.asyncio import Redis
    from redis.exceptions import ConnectionError as RedisConnectionError

    from app.modules.auth.security import digest

    client, _, settings = auth_env
    await account(auth_env)
    org = await organization(client)
    user_id = (await client.get("/api/v1/auth/me")).json()["id"]
    assert settings.redis_url is not None
    async with Redis.from_url(settings.redis_url.get_secret_value()) as redis:
        await redis.set(
            f"{settings.rate_limit_prefix}:invitations:create:user:{digest(user_id)}", 20, ex=60
        )
    assert (
        await client.post(
            f"/api/v1/organizations/{org}/invitations", json={"email": "guest@example.com"}
        )
    ).status_code == 429
    with patch(
        "redis.asyncio.Redis.eval", AsyncMock(side_effect=RedisConnectionError("secret-sentinel"))
    ):
        response = await client.get(f"/api/v1/organizations/{org}")
        assert response.status_code == 503 and "secret-sentinel" not in response.text
    async with Redis.from_url(settings.redis_url.get_secret_value()) as redis:
        await redis.set(
            f"{settings.rate_limit_prefix}:ip:organizations:{digest('127.0.0.1')}", 120, ex=60
        )
    for _ in range(2):
        assert (await client.get(f"/api/v1/organizations/{uuid4()}")).status_code == 429


async def test_m2_upgrade_preserves_m1_accounts_and_sessions(auth_env: Env) -> None:
    client, engine, _ = auth_env
    await account(auth_env)
    before = (await client.get("/api/v1/auth/me")).json()
    async with engine.begin() as conn:

        def migrate(connection: object) -> None:
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = connection
            # Only the disposable schema is downgraded; no tenant rows exist here.
            command.downgrade(cfg, "0001_auth")
            command.upgrade(cfg, "head")
            command.check(cfg)

        await conn.run_sync(migrate)
    assert (await client.get("/api/v1/auth/me")).json() == before
    await organization(client)


async def test_local_verification_disabled_allows_organization_and_invitation_access(
    auth_env: Env,
) -> None:
    client, _, settings = auth_env
    settings.require_email_verification = False
    await account(auth_env, verified=False)
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["email_verified_at"] is None
    assert me["email_verification_required"] is False
    org = await organization(client)
    assert (await client.get(f"/api/v1/organizations/{org}")).status_code == 200
    assert (await client.get(f"/api/v1/organizations/{org}/workflows")).status_code == 200
    invited = await client.post(
        f"/api/v1/organizations/{org}/invitations", json={"email": "local-invitee@example.com"}
    )
    assert invited.status_code == 201
    await account(auth_env, "local-invitee@example.com", verified=False)
    assert (await client.get("/api/v1/invitations")).status_code == 200
    assert (
        await client.post(f"/api/v1/invitations/{invited.json()['id']}/accept")
    ).status_code == 200
    assert (await client.get(f"/api/v1/organizations/{org}")).status_code == 200
    assert (await client.get("/api/v1/auth/me")).json()["email_verified_at"] is None
    settings.require_email_verification = True
    assert (await client.get(f"/api/v1/organizations/{org}")).status_code == 403
