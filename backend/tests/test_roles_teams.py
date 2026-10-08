import asyncio
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_auth_integration import pytestmark  # noqa: F401
from test_organizations import Env, account, cookie, invitation, organization

from app.db.models import AuditEvent, Membership, Organization, TeamMember
from app.modules.auth.security import digest


async def join(env: Env, org: str, owner: str, email: str) -> tuple[str, str]:
    client, _, _ = env
    invite = await invitation(client, org, email, owner)
    raw = await account(env, email)
    assert (await client.post(f"/api/v1/invitations/{invite}/accept")).status_code == 200
    people = (await client.get(f"/api/v1/organizations/{org}/members")).json()["items"]
    return raw, next(row["id"] for row in people if row["email"] == email)


async def assign(
    client: httpx.AsyncClient, org: str, member: str, role: str, actor: str
) -> httpx.Response:
    return await client.patch(
        f"/api/v1/organizations/{org}/members/{member}/role",
        json={"role_code": role},
        headers=cookie(actor),
    )


async def team(client: httpx.AsyncClient, org: str, owner: str, name: str = "Finance") -> str:
    response = await client.post(
        f"/api/v1/organizations/{org}/teams", json={"name": name}, headers=cookie(owner)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.mark.parametrize("role", ["owner", "admin", "designer", "approver", "member", "viewer"])
async def test_role_matrix_all_m3_actions(auth_env: Env, role: str) -> None:
    client, _, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    base = f"/api/v1/organizations/{org}"
    owner_id = (await client.get(f"{base}/members")).json()["items"][0]["id"]
    actor, actor_id = (
        (owner, owner_id)
        if role == "owner"
        else await join(auth_env, org, owner, "actor@example.com")
    )
    if role not in {"owner", "member"}:
        assert (await assign(client, org, actor_id, role, owner)).status_code == 204
    _, target = await join(auth_env, org, owner, "target@example.com")
    _, admin = await join(auth_env, org, owner, "admin@example.com")
    assert (await assign(client, org, admin, "admin", owner)).status_code == 204
    group = await team(client, org, owner)
    invite = await invitation(client, org, "pending@example.com", owner)
    headers = cookie(actor)
    manager = role in {"owner", "admin"}
    for path in ("", "/members", "/roles", "/teams", f"/teams/{group}/members"):
        assert (await client.get(base + path, headers=headers)).status_code == 200
    access = (await client.get(base + "/access", headers=headers)).json()
    assert access["role_code"] == role
    expected = {"directory:read"}
    if role != "owner":
        expected.add("membership:leave")
    if manager:
        expected |= {
            "organization:update",
            "invitation:manage",
            "member:remove",
            "role:assign",
            "team:manage",
        }
    if role == "owner":
        expected.add("role:assign_admin")
    expected.add("workflow:read")
    if role in {"owner", "admin", "designer"}:
        expected |= {"workflow:create", "workflow:edit"}
    if manager:
        expected.add("workflow:publish")
    assert set(access["permissions"]) == expected
    assert (await client.patch(base, json={"name": "Renamed"}, headers=headers)).status_code == (
        200 if manager else 403
    )
    assert (await client.get(base + "/invitations", headers=headers)).status_code == (
        200 if manager else 403
    )
    assert (
        await client.post(base + "/invitations", json={"email": "new@example.com"}, headers=headers)
    ).status_code == (201 if manager else 403)
    assert (
        await client.post(f"{base}/invitations/{invite}/renew", headers=headers)
    ).status_code == (200 if manager else 403)
    assert (await client.delete(f"{base}/invitations/{invite}", headers=headers)).status_code == (
        200 if manager else 403
    )
    for new_role in ("designer", "approver", "viewer", "member"):
        assert (await assign(client, org, target, new_role, actor)).status_code == (
            204 if manager else 403
        )
    assert (await assign(client, org, admin, "member", actor)).status_code == (
        204 if role == "owner" else 403
    )
    assert (await assign(client, org, admin, "admin", actor)).status_code == (
        204 if role == "owner" else 403
    )
    assert (await client.delete(f"{base}/members/{admin}", headers=headers)).status_code == (
        204 if role == "owner" else 403
    )
    assert (
        await client.post(base + "/teams", json={"name": "New team"}, headers=headers)
    ).status_code == (201 if manager else 403)
    assert (
        await client.patch(f"{base}/teams/{group}", json={"name": "Renamed team"}, headers=headers)
    ).status_code == (200 if manager else 403)
    assert (
        await client.post(
            f"{base}/teams/{group}/members", json={"membership_id": target}, headers=headers
        )
    ).status_code == (204 if manager else 403)
    if not manager:
        assert (
            await client.post(
                f"{base}/teams/{group}/members",
                json={"membership_id": target},
                headers=cookie(owner),
            )
        ).status_code == 204
    assert (
        await client.delete(f"{base}/teams/{group}/members/{target}", headers=headers)
    ).status_code == (204 if manager else 403)
    assert (await client.delete(f"{base}/teams/{group}", headers=headers)).status_code == (
        204 if manager else 403
    )
    assert (await client.delete(f"{base}/members/{target}", headers=headers)).status_code == (
        204 if manager else 403
    )
    assert (await client.delete(f"{base}/members/{actor_id}", headers=headers)).status_code == (
        409 if role == "owner" else 204
    )


async def test_owner_protection_admin_escalation_and_immediate_revocation(auth_env: Env) -> None:
    client, engine, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    base = f"/api/v1/organizations/{org}"
    owner_id = (await client.get(base + "/members")).json()["items"][0]["id"]
    admin, admin_id = await join(auth_env, org, owner, "admin@example.com")
    assert (await assign(client, org, admin_id, "admin", owner)).status_code == 204
    assert (await assign(client, org, admin_id, "member", admin)).status_code == 403
    assert (await assign(client, org, owner_id, "member", admin)).status_code == 409
    assert (await assign(client, org, owner_id, "admin", owner)).status_code == 409
    for invalid in ("owner", "superadmin", ""):
        assert (await assign(client, org, admin_id, invalid, owner)).status_code == 422
    assert (
        await client.delete(f"{base}/members/{owner_id}", headers=cookie(admin))
    ).status_code == 409
    # Hold the same tenant lock as requests. The waiting request must see the committed demotion.
    async with async_sessionmaker(engine)() as db:
        await db.scalar(select(Organization).where(Organization.id == UUID(org)).with_for_update())
        await db.execute(
            update(Membership).where(Membership.id == UUID(admin_id)).values(role_code="member")
        )
        pending = asyncio.create_task(
            client.patch(base, json={"name": "Forbidden"}, headers=cookie(admin))
        )
        await asyncio.sleep(0.1)
        await db.commit()
        assert (await pending).status_code == 403
    assert (await client.get(base + "/access", headers=cookie(admin))).json()[
        "role_code"
    ] == "member"
    # Promote and demote through the public API and check an already-authenticated session.
    assert (await assign(client, org, admin_id, "admin", owner)).status_code == 204
    assert (await assign(client, org, admin_id, "viewer", owner)).status_code == 204
    assert (
        await client.post(base + "/teams", json={"name": "Forbidden"}, headers=cookie(admin))
    ).status_code == 403
    async with async_sessionmaker(engine)() as db:
        events = list(
            await db.scalars(
                select(AuditEvent).where(AuditEvent.action == "membership.role_changed")
            )
        )
        assert len(events) == 3
        assert events[-1].details is not None
        assert all(
            row.resource_id == UUID(admin_id) and row.organization_id == UUID(org) for row in events
        )


async def test_role_team_tenant_isolation_and_database_constraints(auth_env: Env) -> None:
    client, engine, _ = auth_env
    alice = await account(auth_env)
    a = await organization(client)
    a_id = (await client.get(f"/api/v1/organizations/{a}/members")).json()["items"][0]["id"]
    a_team = await team(client, a, alice)
    bob = await account(auth_env, "bob@example.com")
    b = await organization(client)
    b_team = await team(client, b, bob)
    for org in (a, b):
        base = f"/api/v1/organizations/{org}"
        assert (await assign(client, org, a_id, "admin", bob)).status_code == 404
        for method, suffix, body in (
            ("GET", f"/teams/{a_team}/members", None),
            ("PATCH", f"/teams/{a_team}", {"name": "Stolen"}),
            ("DELETE", f"/teams/{a_team}", None),
            ("POST", f"/teams/{a_team}/members", {"membership_id": a_id}),
            ("DELETE", f"/teams/{a_team}/members/{a_id}", None),
        ):
            assert (await client.request(method, base + suffix, json=body)).status_code == 404
    for suffix in ("/roles", "/access", "/teams"):
        assert (await client.get(f"/api/v1/organizations/{a}{suffix}")).status_code == 404
    assert (
        await client.post(
            f"/api/v1/organizations/{b}/teams/{b_team}/members", json={"membership_id": a_id}
        )
    ).status_code == 404
    # Even a direct SQL write cannot attach another tenant's membership or team.
    for org, group in ((b, b_team), (b, a_team)):
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    insert(TeamMember).values(
                        organization_id=UUID(org), team_id=UUID(group), membership_id=UUID(a_id)
                    )
                )


async def test_team_lifecycle_pagination_audit_and_rejoin_resets_access(auth_env: Env) -> None:
    client, engine, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    base = f"/api/v1/organizations/{org}"
    member, member_id = await join(auth_env, org, owner, "member@example.com")
    owner_id = next(
        row["id"]
        for row in (await client.get(base + "/members")).json()["items"]
        if row["email"] == "alice@example.com"
    )
    assert (await assign(client, org, member_id, "admin", owner)).status_code == 204
    one = await team(client, org, owner, "One")
    two = await team(client, org, owner, "Two")
    for person in (owner_id, member_id):
        assert (
            await client.post(f"{base}/teams/{one}/members", json={"membership_id": person})
        ).status_code == 204
    assert (
        await client.post(f"{base}/teams/{one}/members", json={"membership_id": member_id})
    ).status_code == 409
    assert (await client.post(base + "/teams", json={"name": " One "})).status_code == 409
    assert (await client.patch(f"{base}/teams/{two}", json={"name": "One"})).status_code == 409
    for suffix, expected in (
        ("/teams", {one, two}),
        (f"/teams/{one}/members", {owner_id, member_id}),
    ):
        first = (await client.get(base + suffix + "?limit=1")).json()
        second = (
            await client.get(base + suffix + f"?limit=1&cursor={first['next_cursor']}")
        ).json()
        assert {first["items"][0]["id"], second["items"][0]["id"]} == expected
        assert second["next_cursor"] is None
    assert (await client.delete(f"{base}/teams/{one}/members/{owner_id}")).status_code == 204
    assert (await client.patch(f"{base}/teams/{one}", json={"name": "Renamed"})).status_code == 200
    assert (
        await client.delete(f"{base}/members/{member_id}", headers=cookie(owner))
    ).status_code == 204
    assert (await client.get(base + "/access", headers=cookie(member))).status_code == 404
    again = await invitation(client, org, "member@example.com", owner)
    assert (
        await client.post(f"/api/v1/invitations/{again}/accept", headers=cookie(member))
    ).status_code == 200
    assert (await client.get(base + "/access", headers=cookie(member))).json()[
        "role_code"
    ] == "member"
    assert (await client.get(f"{base}/teams/{one}/members")).json()["items"] == []
    assert (
        await client.post(
            f"{base}/teams/{two}/members", json={"membership_id": owner_id}, headers=cookie(owner)
        )
    ).status_code == 204
    assert (await client.delete(f"{base}/teams/{two}", headers=cookie(owner))).status_code == 204
    assert len((await client.get(base + "/members")).json()["items"]) == 2
    async with async_sessionmaker(engine)() as db:
        assert await db.scalar(select(func.count()).select_from(TeamMember)) == 0
        events = list(
            await db.scalars(select(AuditEvent).where(AuditEvent.organization_id == UUID(org)))
        )
        assert {row.action for row in events} >= {
            "team.created",
            "team.renamed",
            "team.deleted",
            "team.member_added",
            "team.member_removed",
            "membership.role_changed",
        }
        added = next(row for row in events if row.action == "team.member_added")
        assert added.details is not None and "membership_id" in added.details


async def test_concurrent_team_add_remove_and_role_change(auth_env: Env) -> None:
    client, engine, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    _, member_id = await join(auth_env, org, owner, "member@example.com")
    group = await team(client, org, owner)
    base = f"/api/v1/organizations/{org}"
    replies = await asyncio.gather(
        *[
            client.post(
                f"{base}/teams/{group}/members",
                json={"membership_id": member_id},
                headers=cookie(owner),
            )
            for _ in range(2)
        ]
    )
    assert sorted(row.status_code for row in replies) == [204, 409]
    removed, assigned = await asyncio.gather(
        client.delete(f"{base}/members/{member_id}", headers=cookie(owner)),
        assign(client, org, member_id, "admin", owner),
    )
    assert removed.status_code == 204 and assigned.status_code in {204, 404}
    async with async_sessionmaker(engine)() as db:
        row = await db.get(Membership, UUID(member_id))
        assert row is not None and row.revoked_at is not None and row.role_code == "member"
        assert await db.scalar(select(func.count()).select_from(TeamMember)) == 0
    assert (
        await client.post(
            f"{base}/teams/{group}/members",
            json={"membership_id": member_id},
            headers=cookie(owner),
        )
    ).status_code == 404


async def test_team_and_role_csrf_validation_shared_limits_and_redaction(auth_env: Env) -> None:
    from unittest.mock import AsyncMock, patch

    from redis.exceptions import ConnectionError as RedisConnectionError

    client, _, settings = auth_env
    assert (
        await client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000/roles")
    ).status_code == 401
    owner = await account(auth_env)
    org = await organization(client)
    base = f"/api/v1/organizations/{org}"
    person = (await client.get(base + "/members")).json()["items"][0]
    for method, suffix, body in (
        ("POST", "/teams", {"name": "Bad"}),
        ("PATCH", f"/members/{person['id']}/role", {"role_code": "admin"}),
    ):
        assert (
            await client.request(
                method, base + suffix, json=body, headers={"Origin": "https://evil.example"}
            )
        ).status_code == 403
    for body in ({"name": " "}, {"name": "x" * 121}, {"name": "valid", "organization_id": org}):
        assert (await client.post(base + "/teams", json=body)).status_code == 422
    assert (await client.get(base + "/teams?limit=101")).status_code == 422
    group = await team(client, org, owner)
    assert (
        await client.post(
            f"{base}/teams/{group}/members", json={"membership_id": "secret-sentinel"}
        )
    ).status_code == 422
    with patch(
        "redis.asyncio.Redis.eval", AsyncMock(side_effect=RedisConnectionError("secret-sentinel"))
    ):
        response = await client.get(base + "/roles")
        assert response.status_code == 503 and "secret-sentinel" not in response.text
    assert settings.redis_url is not None
    async with Redis.from_url(settings.redis_url.get_secret_value()) as redis:
        await redis.set(
            f"{settings.rate_limit_prefix}:organizations:user:{digest(person['user_id'])}",
            120,
            ex=60,
        )
    for suffix in ("/roles", "/teams", "/access"):
        response = await client.get(base + suffix)
        assert response.status_code == 429 and response.headers["cache-control"] == "no-store"


async def test_m3_migration_preserves_existing_m2_data_and_backfills_roles(auth_env: Env) -> None:
    client, engine, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    _, member_id = await join(auth_env, org, owner, "member@example.com")
    pending = await invitation(client, org, "pending@example.com", owner)
    before = (await client.get("/api/v1/auth/me")).json()
    async with engine.begin() as conn:

        def migrate(connection: object) -> None:
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = connection
            # Downgrade only this fixture's disposable schema to model legacy M2 rows.
            command.downgrade(cfg, "0002_organizations")
            command.upgrade(cfg, "head")
            command.check(cfg)

        await conn.run_sync(migrate)
    assert (await client.get("/api/v1/auth/me")).json() == before
    people = (await client.get(f"/api/v1/organizations/{org}/members")).json()["items"]
    assert {row["email"]: row["role_code"] for row in people} == {
        "alice@example.com": "owner",
        "member@example.com": "member",
    }
    assert next(row for row in people if row["id"] == member_id)
    invites = (
        await client.get(f"/api/v1/organizations/{org}/invitations", headers=cookie(owner))
    ).json()["items"]
    assert any(row["id"] == pending for row in invites)
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM audit_events")) > 0
    await team(client, org, owner)


async def test_roles_are_per_organization_and_teams_do_not_grant_permissions(auth_env: Env) -> None:
    client, _, _ = auth_env
    alice = await account(auth_env)
    a = await organization(client)
    invite = await invitation(client, a)
    bob = await account(auth_env, "bob@example.com")
    b = await organization(client, "Bob's organization")
    assert (await client.post(f"/api/v1/invitations/{invite}/accept")).status_code == 200
    a_base = f"/api/v1/organizations/{a}"
    bob_id = next(
        row["id"]
        for row in (await client.get(a_base + "/members")).json()["items"]
        if row["email"] == "bob@example.com"
    )
    group = await team(client, a, alice)
    assert (
        await client.post(
            f"{a_base}/teams/{group}/members", json={"membership_id": bob_id}, headers=cookie(alice)
        )
    ).status_code == 204
    assert (await client.get(a_base + "/access", headers=cookie(bob))).json()[
        "role_code"
    ] == "member"
    assert (await client.get(f"/api/v1/organizations/{b}/access", headers=cookie(bob))).json()[
        "role_code"
    ] == "owner"
    assert (
        await client.patch(a_base, json={"name": "Forbidden"}, headers=cookie(bob))
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/organizations/{b}", json={"name": "Allowed"}, headers=cookie(bob)
        )
    ).status_code == 200


async def test_team_add_racing_organization_removal_cannot_leave_stale_members(
    auth_env: Env,
) -> None:
    client, engine, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    _, member_id = await join(auth_env, org, owner, "member@example.com")
    group = await team(client, org, owner)
    base = f"/api/v1/organizations/{org}"
    added, removed = await asyncio.gather(
        client.post(
            f"{base}/teams/{group}/members",
            json={"membership_id": member_id},
            headers=cookie(owner),
        ),
        client.delete(f"{base}/members/{member_id}", headers=cookie(owner)),
    )
    assert removed.status_code == 204 and added.status_code in {204, 404}
    async with async_sessionmaker(engine)() as db:
        assert await db.scalar(select(func.count()).select_from(TeamMember)) == 0
