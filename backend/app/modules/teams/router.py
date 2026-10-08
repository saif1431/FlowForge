from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.modules.auth.dependencies import Database, protect
from app.modules.auth.schemas import ErrorEnvelope
from app.modules.organizations.router import CurrentUser, Page, Tenant
from app.modules.organizations.schemas import MemberList
from app.modules.teams import service
from app.modules.teams.schemas import TeamInput, TeamList, TeamMemberInput, TeamOutput

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}/teams",
    tags=["teams"],
    dependencies=[Depends(protect)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


@router.get("")
async def listing(db: Database, tenant: Tenant, page: Page) -> TeamList:
    return await service.listing(db, tenant, page)


@router.post("", status_code=201)
async def create(
    body: TeamInput, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> TeamOutput:
    return await service.create(db, tenant, user, body.name, request.state.request_id)


@router.patch("/{team_id}")
async def rename(
    team_id: UUID,
    body: TeamInput,
    request: Request,
    db: Database,
    user: CurrentUser,
    tenant: Tenant,
) -> TeamOutput:
    return await service.rename(db, tenant, user, team_id, body.name, request.state.request_id)


@router.delete("/{team_id}", status_code=204)
async def remove(
    team_id: UUID, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> None:
    await service.remove(db, tenant, user, team_id, request.state.request_id)


@router.get("/{team_id}/members")
async def members(team_id: UUID, db: Database, tenant: Tenant, page: Page) -> MemberList:
    return await service.members(db, tenant, team_id, page)


@router.post("/{team_id}/members", status_code=204)
async def add_member(
    team_id: UUID,
    body: TeamMemberInput,
    request: Request,
    db: Database,
    user: CurrentUser,
    tenant: Tenant,
) -> None:
    await service.change_member(
        db, tenant, user, team_id, body.membership_id, True, request.state.request_id
    )


@router.delete("/{team_id}/members/{member_id}", status_code=204)
async def remove_member(
    team_id: UUID,
    member_id: UUID,
    request: Request,
    db: Database,
    user: CurrentUser,
    tenant: Tenant,
) -> None:
    await service.change_member(
        db, tenant, user, team_id, member_id, False, request.state.request_id
    )
