from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Membership, Team, TeamMember, User
from app.modules.auth.errors import AuthError
from app.modules.organizations import repository as org_repo
from app.modules.organizations.schemas import MemberList, MemberOutput, PageInput
from app.modules.organizations.service import audit
from app.modules.roles.authorization import require
from app.modules.teams import repository as repo
from app.modules.teams.schemas import TeamList, TeamOutput


async def unique_name(
    db: AsyncSession, tenant: org_repo.TenantContext, name: str, team_id: UUID | None = None
) -> None:
    query = select(Team.id).where(Team.organization_id == tenant.id, Team.name == name)
    if team_id is not None:
        query = query.where(Team.id != team_id)
    if await db.scalar(query) is not None:
        raise AuthError(409, "TEAM_NAME_EXISTS", "A team with this name already exists.")


async def listing(db: AsyncSession, tenant: org_repo.TenantContext, page: PageInput) -> TeamList:
    await require(db, tenant, "directory:read")
    query = select(Team).where(Team.organization_id == tenant.id)
    if page.cursor:
        query = query.where(Team.id > page.cursor)
    rows = list(await db.scalars(query.order_by(Team.id).limit(page.limit + 1)))
    result = TeamList(
        items=[TeamOutput.model_validate(row) for row in rows[: page.limit]],
        next_cursor=rows[page.limit - 1].id if len(rows) > page.limit else None,
    )
    await db.commit()
    return result


async def create(
    db: AsyncSession, tenant: org_repo.TenantContext, user: User, name: str, request_id: str
) -> TeamOutput:
    await require(db, tenant, "team:manage")
    await unique_name(db, tenant, name)
    row = Team(organization_id=tenant.id, name=name)
    db.add(row)
    await db.flush()
    audit(db, user, tenant.id, "team.created", request_id, row.id)
    await db.commit()
    return TeamOutput.model_validate(row)


async def rename(
    db: AsyncSession,
    tenant: org_repo.TenantContext,
    user: User,
    team_id: UUID,
    name: str,
    request_id: str,
) -> TeamOutput:
    row = await repo.team(db, tenant, team_id)
    await require(db, tenant, "team:manage")
    await unique_name(db, tenant, name, team_id)
    row.name = name
    audit(db, user, tenant.id, "team.renamed", request_id, row.id)
    await db.commit()
    return TeamOutput.model_validate(row)


async def remove(
    db: AsyncSession, tenant: org_repo.TenantContext, user: User, team_id: UUID, request_id: str
) -> None:
    row = await repo.team(db, tenant, team_id)
    await require(db, tenant, "team:manage")
    audit(db, user, tenant.id, "team.deleted", request_id, row.id)
    await db.delete(row)
    await db.commit()


async def members(
    db: AsyncSession, tenant: org_repo.TenantContext, team_id: UUID, page: PageInput
) -> MemberList:
    await repo.team(db, tenant, team_id)
    await require(db, tenant, "directory:read")
    query = (
        select(Membership, User.email)
        .join(User)
        .join(TeamMember, TeamMember.membership_id == Membership.id)
        .where(
            TeamMember.organization_id == tenant.id,
            TeamMember.team_id == team_id,
            Membership.organization_id == tenant.id,
            Membership.revoked_at.is_(None),
        )
    )
    if page.cursor:
        query = query.where(Membership.id > page.cursor)
    rows = list(await db.execute(query.order_by(Membership.id).limit(page.limit + 1)))
    result = MemberList(
        items=[
            MemberOutput(
                id=row.id,
                user_id=row.user_id,
                email=email,
                created_at=row.created_at,
                role_code=row.role_code,
            )
            for row, email in rows[: page.limit]
        ],
        next_cursor=rows[page.limit - 1][0].id if len(rows) > page.limit else None,
    )
    await db.commit()
    return result


async def change_member(
    db: AsyncSession,
    tenant: org_repo.TenantContext,
    user: User,
    team_id: UUID,
    member_id: UUID,
    adding: bool,
    request_id: str,
) -> None:
    await repo.team(db, tenant, team_id)
    await org_repo.membership(db, tenant, member_id)
    await require(db, tenant, "team:manage")
    query = select(TeamMember).where(
        TeamMember.organization_id == tenant.id,
        TeamMember.team_id == team_id,
        TeamMember.membership_id == member_id,
    )
    existing = await db.scalar(query)
    if adding:
        if existing is not None:
            raise AuthError(409, "ALREADY_TEAM_MEMBER", "This member is already in the team.")
        db.add(TeamMember(organization_id=tenant.id, team_id=team_id, membership_id=member_id))
    else:
        if existing is None:
            raise org_repo.missing()
        await db.execute(
            delete(TeamMember).where(
                TeamMember.organization_id == tenant.id,
                TeamMember.team_id == team_id,
                TeamMember.membership_id == member_id,
            )
        )
    audit(
        db,
        user,
        tenant.id,
        "team.member_added" if adding else "team.member_removed",
        request_id,
        team_id,
        {"membership_id": str(member_id)},
    )
    await db.commit()
