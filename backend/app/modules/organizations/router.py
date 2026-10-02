from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.db.models import User
from app.modules.auth.dependencies import Database, config, limit, protect
from app.modules.auth.schemas import EmailInput, ErrorEnvelope
from app.modules.auth.service import authenticate
from app.modules.organizations import repository, service
from app.modules.organizations.schemas import (
    InvitationList,
    InvitationOutput,
    MemberList,
    OrganizationInput,
    OrganizationList,
    OrganizationOutput,
    PageInput,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["organizations"],
    dependencies=[Depends(protect)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


async def current_user(request: Request, db: Database) -> User:
    settings = config(request)
    user, _ = await authenticate(db, request.cookies.get(settings.session_cookie), settings)
    await limit(request, "organizations:user", str(user.id), 120, 60)
    return user


CurrentUser = Annotated[User, Depends(current_user)]
Page = Annotated[PageInput, Query()]


async def context(org_id: UUID, db: Database, user: CurrentUser) -> repository.TenantContext:
    service.verified(user)
    return await repository.resolve(db, org_id, user.id)


Tenant = Annotated[repository.TenantContext, Depends(context)]


@router.post("/organizations", status_code=201)
async def create(
    body: OrganizationInput, request: Request, db: Database, user: CurrentUser
) -> OrganizationOutput:
    await limit(request, "organizations:create", str(user.id), 10, 3600)
    return await service.create(db, user, body.name, request.state.request_id)


@router.get("/organizations")
async def list_organizations(db: Database, user: CurrentUser, page: Page) -> OrganizationList:
    service.verified(user)
    return await service.organizations(db, user, page)


@router.get("/organizations/{org_id}")
async def detail(db: Database, tenant: Tenant) -> OrganizationOutput:
    result = OrganizationOutput.model_validate(tenant.organization)
    await db.commit()
    return result


@router.patch("/organizations/{org_id}")
async def rename(
    body: OrganizationInput, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> OrganizationOutput:
    return await service.rename(db, tenant, user, body.name, request.state.request_id)


@router.get("/organizations/{org_id}/members")
async def members(db: Database, tenant: Tenant, page: Page) -> MemberList:
    return await service.members(db, tenant, page)


@router.delete("/organizations/{org_id}/members/{member_id}", status_code=204)
async def remove_member(
    member_id: UUID, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> None:
    await service.remove_member(db, tenant, user, member_id, request.state.request_id)


@router.post("/organizations/{org_id}/invitations", status_code=201)
async def invite(
    body: EmailInput, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> InvitationOutput:
    await limit(request, "invitations:create:user", str(user.id), 20, 3600)
    await limit(request, "invitations:create:org", str(tenant.id), 50, 3600)
    return await service.invite(db, tenant, user, body.email, request.state.request_id)


@router.get("/organizations/{org_id}/invitations")
async def sent_invitations(
    db: Database, user: CurrentUser, tenant: Tenant, page: Page
) -> InvitationList:
    return await service.invitations(db, user, page, tenant)


@router.delete("/organizations/{org_id}/invitations/{invitation_id}")
async def revoke(
    invitation_id: UUID, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> InvitationOutput:
    return await service.manage_invitation(
        db, tenant, user, invitation_id, "revoke", request.state.request_id
    )


@router.post("/organizations/{org_id}/invitations/{invitation_id}/renew")
async def renew(
    invitation_id: UUID, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> InvitationOutput:
    await limit(request, "invitations:renew", str(user.id), 20, 3600)
    return await service.manage_invitation(
        db, tenant, user, invitation_id, "renew", request.state.request_id
    )


@router.get("/invitations")
async def received_invitations(db: Database, user: CurrentUser, page: Page) -> InvitationList:
    return await service.invitations(db, user, page)


@router.post("/invitations/{invitation_id}/accept")
async def accept(
    invitation_id: UUID, request: Request, db: Database, user: CurrentUser
) -> InvitationOutput:
    return await service.respond(db, user, invitation_id, "accept", request.state.request_id)


@router.post("/invitations/{invitation_id}/decline")
async def decline(
    invitation_id: UUID, request: Request, db: Database, user: CurrentUser
) -> InvitationOutput:
    return await service.respond(db, user, invitation_id, "decline", request.state.request_id)
