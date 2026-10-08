from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.modules.auth.dependencies import Database, protect
from app.modules.auth.schemas import ErrorEnvelope
from app.modules.organizations.router import CurrentUser, Tenant
from app.modules.roles import service
from app.modules.roles.schemas import AccessOutput, RoleInput, RoleList

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}",
    tags=["roles"],
    dependencies=[Depends(protect)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


@router.get("/access")
async def access(db: Database, tenant: Tenant) -> AccessOutput:
    return await service.access(db, tenant)


@router.get("/roles")
async def catalog(db: Database, tenant: Tenant) -> RoleList:
    return await service.catalog(db, tenant)


@router.patch("/members/{member_id}/role", status_code=204)
async def assign(
    member_id: UUID,
    body: RoleInput,
    request: Request,
    db: Database,
    user: CurrentUser,
    tenant: Tenant,
) -> None:
    await service.assign(db, tenant, user, member_id, body.role_code, request.state.request_id)
