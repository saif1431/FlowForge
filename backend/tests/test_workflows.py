import asyncio
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_auth_integration import pytestmark  # noqa: F401
from test_organizations import Env, account, cookie, organization
from test_roles_teams import assign, join, team
from workflow_helpers import graph

from app.db.models import AuditEvent, WorkflowVersion


async def create(
    client: httpx.AsyncClient, org: str, actor: str | None = None
) -> tuple[str, dict[str, Any]]:
    response = await client.post(
        f"/api/v1/organizations/{org}/workflows",
        json={"name": "Purchase review", "description": "M4 test"},
        headers=cookie(actor) if actor else {},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return f"/api/v1/organizations/{org}/workflows/{body['workflow']['id']}", body["draft"]


async def save(
    client: httpx.AsyncClient,
    base: str,
    draft: dict[str, Any],
    data: dict[str, Any],
    actor: str | None = None,
) -> httpx.Response:
    return await client.put(
        f"{base}/versions/{draft['id']}/graph",
        json={"expected_revision": draft["revision"], "graph": data},
        headers=cookie(actor) if actor else {},
    )


async def publish(
    client: httpx.AsyncClient, base: str, draft: dict[str, Any], actor: str | None = None
) -> httpx.Response:
    return await client.post(
        f"{base}/versions/{draft['id']}/publish",
        json={"expected_revision": draft["revision"]},
        headers=cookie(actor) if actor else {},
    )


async def test_workflow_lifecycle_immutable_snapshot_and_audit(auth_env: Env) -> None:
    client, engine, _ = auth_env
    await account(auth_env)
    org = await organization(client)
    base, draft = await create(client, org)
    assert draft["status"] == "draft" and draft["revision"] == 1
    saved = await save(client, base, draft, graph())
    assert saved.status_code == 200, saved.text
    draft = saved.json()
    report = await client.post(
        f"{base}/versions/{draft['id']}/validate", json={"expected_revision": 2}
    )
    assert report.json() == {"valid": True, "issues": []}
    published = await publish(client, base, draft)
    assert published.status_code == 200
    snapshot = published.json()
    assert snapshot["status"] == "published" and snapshot["published_at"]
    assert (await save(client, base, snapshot, graph())).json()["error"][
        "code"
    ] == "VERSION_IMMUTABLE"
    assert (await publish(client, base, snapshot)).status_code == 409
    cloned = await client.post(base + "/drafts", json={"source_version_id": snapshot["id"]})
    assert cloned.status_code == 201
    draft2 = cloned.json()
    assert draft2["version_number"] == 2 and draft2["graph"] == snapshot["graph"]
    assert (await client.post(base + "/drafts", json={})).status_code == 409
    data = draft2["graph"]
    data["nodes"][0]["label"] = "Changed in draft only"
    assert (await save(client, base, draft2, data)).status_code == 200
    assert (await client.get(f"{base}/versions/{snapshot['id']}")).json() == snapshot
    versions = (await client.get(base + "/versions?limit=1")).json()
    next_page = (
        await client.get(base + f"/versions?limit=1&cursor={versions['next_cursor']}")
    ).json()
    assert {versions["items"][0]["id"], next_page["items"][0]["id"]} == {
        snapshot["id"],
        draft2["id"],
    }
    async with async_sessionmaker(engine)() as db:
        events = list(
            await db.scalars(select(AuditEvent).where(AuditEvent.organization_id == UUID(org)))
        )
        assert {event.action for event in events} >= {
            "workflow.created",
            "workflow.draft_created",
            "workflow.draft_saved",
            "workflow.published",
        }
        assert sum(event.action == "workflow.published" for event in events) == 1
        assert all("nodes" not in (event.details or {}) for event in events)


async def test_invalid_drafts_validate_but_cannot_publish_and_bad_references_rollback(
    auth_env: Env,
) -> None:
    client, _, _ = auth_env
    await account(auth_env)
    org = await organization(client)
    base, draft = await create(client, org)
    invalid = await publish(client, base, draft)
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["issues"][0]["code"] == "TRIGGER_COUNT"
    assert (await client.get(f"{base}/versions/{draft['id']}")).json() == draft
    data = graph()
    data["edges"][0]["target"] = str(uuid4())
    assert (await save(client, base, draft, data)).status_code == 422
    assert (await client.get(f"{base}/versions/{draft['id']}")).json() == draft
    incomplete = graph("condition")
    saved = await save(client, base, draft, incomplete)
    assert saved.status_code == 200
    assert (await publish(client, base, saved.json())).status_code == 422


@pytest.mark.parametrize("role", ["owner", "admin", "designer", "approver", "member", "viewer"])
async def test_workflow_role_permissions(auth_env: Env, role: str) -> None:
    client, _, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    base, draft = await create(client, org)
    if role == "owner":
        actor = owner
    else:
        actor, member_id = await join(auth_env, org, owner, "actor@example.com")
        assert (await assign(client, org, member_id, role, owner)).status_code == 204
    can_edit = role in {"owner", "admin", "designer"}
    headers = cookie(actor)
    for path in (base, base + "/versions", f"{base}/versions/{draft['id']}"):
        assert (await client.get(path, headers=headers)).status_code == 200
    assert (
        await client.post(base.rsplit("/", 1)[0], json={"name": "Another"}, headers=headers)
    ).status_code == (201 if can_edit else 403)
    response = await save(client, base, draft, graph(), actor)
    assert response.status_code == (200 if can_edit else 403)
    if not can_edit:
        response = await save(client, base, draft, graph(), owner)
    draft = response.json()
    assert (await publish(client, base, draft, actor)).status_code == (
        200 if role in {"owner", "admin"} else 403
    )


async def test_workflow_tenant_and_version_substitution(auth_env: Env) -> None:
    client, _, _ = auth_env
    alice = await account(auth_env)
    a = await organization(client)
    base_a, draft_a = await create(client, a)
    second, _ = await create(client, a)
    assert (await client.get(f"{second}/versions/{draft_a['id']}")).status_code == 404
    await account(auth_env, "bob@example.com")
    b = await organization(client)
    base_b, _ = await create(client, b)
    for base in (base_a, base_b):
        assert (await client.get(f"{base}/versions/{draft_a['id']}")).status_code == 404
        assert (await save(client, base, draft_a, graph())).status_code == 404
        assert (await publish(client, base, draft_a)).status_code == 404
        assert (
            await client.post(
                f"{base}/versions/{draft_a['id']}/validate", json={"expected_revision": 1}
            )
        ).status_code == 404
    assert (await client.get(base_a)).status_code == 404
    assert (await client.get(f"/api/v1/organizations/{a}/workflows")).status_code == 404
    assert (await client.post(base_a + "/drafts", json={})).status_code == 404
    # Source-version substitution is also rejected after the target has no draft.
    response = await save(
        client, base_b, (await client.get(base_b + "/versions")).json()["items"][0], graph()
    )
    assert (await publish(client, base_b, response.json())).status_code == 200
    assert (
        await client.post(base_b + "/drafts", json={"source_version_id": draft_a["id"]})
    ).status_code == 404
    assert (await client.get(base_a, headers=cookie(alice))).status_code == 200


async def test_concurrent_save_publish_and_clone(auth_env: Env) -> None:
    client, engine, _ = auth_env
    await account(auth_env)
    org = await organization(client)
    base, draft = await create(client, org)
    first, second = await asyncio.gather(
        save(client, base, draft, graph()), save(client, base, draft, graph())
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    draft = next(response.json() for response in (first, second) if response.status_code == 200)
    saving, publishing = await asyncio.gather(
        save(client, base, draft, graph()), publish(client, base, draft)
    )
    assert sorted([saving.status_code, publishing.status_code]) == [200, 409]
    if saving.status_code == 200:
        assert (await publish(client, base, saving.json())).status_code == 200
    clones = await asyncio.gather(*[client.post(base + "/drafts", json={}) for _ in range(2)])
    assert sorted(response.status_code for response in clones) == [201, 409]
    new = next(response.json() for response in clones if response.status_code == 201)
    published = await asyncio.gather(publish(client, base, new), publish(client, base, new))
    assert sorted(response.status_code for response in published) == [200, 409]
    async with async_sessionmaker(engine)() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "workflow.published")
            )
            == 2
        )
        assert await db.scalar(select(func.count()).select_from(WorkflowVersion)) == 2


async def test_approval_references_validated_again_at_publication(auth_env: Env) -> None:
    client, _, _ = auth_env
    owner = await account(auth_env)
    org = await organization(client)
    _, member = await join(auth_env, org, owner, "approver@example.com")
    assert (await assign(client, org, member, "approver", owner)).status_code == 204
    base, draft = await create(client, org, owner)
    saved = (
        await save(
            client,
            base,
            draft,
            graph("approval", {"assignee": {"kind": "member", "id": member}}),
            owner,
        )
    ).json()
    assert (
        await client.post(
            f"{base}/versions/{saved['id']}/validate",
            json={"expected_revision": saved["revision"]},
            headers=cookie(owner),
        )
    ).json()["valid"]
    assert (await assign(client, org, member, "member", owner)).status_code == 204
    assert (await publish(client, base, saved, owner)).json()["error"]["details"]["issues"][0][
        "code"
    ] == "APPROVER_UNAVAILABLE"
    group = await team(client, org, owner)
    saved = (
        await save(
            client,
            base,
            saved,
            graph("approval", {"assignee": {"kind": "team", "id": group}}),
            owner,
        )
    ).json()
    assert (await publish(client, base, saved, owner)).status_code == 422
    owner_id = next(
        row["id"]
        for row in (
            await client.get(f"/api/v1/organizations/{org}/members", headers=cookie(owner))
        ).json()["items"]
        if row["email"] == "alice@example.com"
    )
    assert (
        await client.post(
            f"/api/v1/organizations/{org}/teams/{group}/members",
            json={"membership_id": owner_id},
            headers=cookie(owner),
        )
    ).status_code == 204
    assert (await publish(client, base, saved, owner)).status_code == 200


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE workflow_versions SET status = 'draft', published_at = NULL WHERE id = :version",
        "DELETE FROM workflow_versions WHERE id = :version",
        "UPDATE workflow_nodes SET label = 'changed' WHERE version_id = :version",
        "DELETE FROM workflow_nodes WHERE version_id = :version",
        "UPDATE workflow_edges SET branch = 'false' WHERE version_id = :version",
        "DELETE FROM workflow_edges WHERE version_id = :version",
        "INSERT INTO workflow_nodes SELECT version_id, :new_id, organization_id, kind, label, config, position_x, position_y FROM workflow_nodes WHERE version_id = :version LIMIT 1",
        "INSERT INTO workflow_edges SELECT version_id, :new_id, organization_id, source, target, branch FROM workflow_edges WHERE version_id = :version LIMIT 1",
    ],
)
async def test_database_rejects_direct_published_mutation(auth_env: Env, statement: str) -> None:
    client, engine, _ = auth_env
    await account(auth_env)
    org = await organization(client)
    base, draft = await create(client, org)
    saved = (await save(client, base, draft, graph())).json()
    assert (await publish(client, base, saved)).status_code == 200
    with pytest.raises(IntegrityError) as failure:
        async with engine.begin() as conn:
            await conn.execute(text(statement), {"version": UUID(draft["id"]), "new_id": uuid4()})
    assert getattr(failure.value.orig, "sqlstate", None) == "23514"


async def test_m4_upgrade_preserves_m3_memberships_and_roles(auth_env: Env) -> None:
    client, engine, _ = auth_env
    await account(auth_env)
    org = await organization(client)
    before = (await client.get(f"/api/v1/organizations/{org}/members")).json()
    async with engine.begin() as conn:

        def migrate(connection: object) -> None:
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = connection
            command.downgrade(cfg, "0003_roles_teams")
            command.upgrade(cfg, "head")
            command.check(cfg)

        await conn.run_sync(migrate)
    assert (await client.get(f"/api/v1/organizations/{org}/members")).json() == before
    await create(client, org)


async def test_workflow_csrf_limits_and_secret_redaction(auth_env: Env) -> None:
    from redis.asyncio import Redis

    from app.modules.auth.security import digest

    client, _, settings = auth_env
    await account(auth_env)
    org = await organization(client)
    base, draft = await create(client, org)
    path = f"{base}/versions/{draft['id']}/graph"
    response = await client.options(
        path,
        headers={
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type,x-csrf-protection",
        },
    )
    assert response.status_code == 200
    assert (
        await client.put(
            path,
            json={"expected_revision": 1, "graph": graph()},
            headers={"Origin": "https://evil.example"},
        )
    ).status_code == 403
    data = graph("webhook", {"url": "https://example.com?token=secret-sentinel"})
    response = await save(client, base, draft, data)
    assert response.status_code == 422 and "secret-sentinel" not in response.text
    assert (await client.put(path, content="x" * 16385)).status_code == 413
    user = (await client.get("/api/v1/auth/me")).json()["id"]
    assert settings.redis_url is not None
    async with Redis.from_url(settings.redis_url.get_secret_value()) as redis:
        await redis.set(f"{settings.rate_limit_prefix}:workflows:create:{digest(user)}", 30, ex=60)
    assert (await client.post(base.rsplit("/", 1)[0], json={"name": "Limited"})).status_code == 429
