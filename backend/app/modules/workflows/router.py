from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.modules.auth.dependencies import Database, limit, protect
from app.modules.auth.schemas import ErrorEnvelope
from app.modules.organizations.router import CurrentUser, Page, Tenant
from app.modules.workflows import service
from app.modules.workflows.schemas import (
    DraftInput,
    GraphValidation,
    RevisionInput,
    SaveGraphInput,
    VersionDetail,
    VersionList,
    VersionPage,
    WorkflowCreated,
    WorkflowInput,
    WorkflowList,
    WorkflowOutput,
)

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}/workflows",
    tags=["workflows"],
    dependencies=[Depends(protect)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


@router.post("", status_code=201)
async def create(
    body: WorkflowInput, request: Request, db: Database, user: CurrentUser, tenant: Tenant
) -> WorkflowCreated:
    await limit(request, "workflows:create", str(user.id), 30, 3600)
    return await service.create(db, tenant, user, body, request.state.request_id)


@router.get("")
async def listing(db: Database, tenant: Tenant, page: Page) -> WorkflowList:
    return await service.listing(db, tenant, page)


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: UUID, db: Database, tenant: Tenant) -> WorkflowOutput:
    return await service.get_workflow(db, tenant, workflow_id)


@router.get("/{workflow_id}/versions")
async def versions(
    workflow_id: UUID, db: Database, tenant: Tenant, page: Annotated[VersionPage, Query()]
) -> VersionList:
    return await service.versions(db, tenant, workflow_id, page)


@router.post("/{workflow_id}/drafts", status_code=201)
async def new_draft(
    workflow_id: UUID,
    body: DraftInput,
    request: Request,
    db: Database,
    user: CurrentUser,
    tenant: Tenant,
) -> VersionDetail:
    return await service.new_draft(
        db, tenant, user, workflow_id, body.source_version_id, request.state.request_id
    )


@router.get("/{workflow_id}/versions/{version_id}")
async def get_version(
    workflow_id: UUID, version_id: UUID, db: Database, tenant: Tenant
) -> VersionDetail:
    return await service.get_version(db, tenant, workflow_id, version_id)


@router.put("/{workflow_id}/versions/{version_id}/graph")
async def save(
    workflow_id: UUID,
    version_id: UUID,
    body: SaveGraphInput,
    request: Request,
    db: Database,
    user: CurrentUser,
    tenant: Tenant,
) -> VersionDetail:
    return await service.save(
        db,
        tenant,
        user,
        workflow_id,
        version_id,
        body.expected_revision,
        body.graph,
        request.state.request_id,
    )


@router.post("/{workflow_id}/versions/{version_id}/validate")
async def validate(
    workflow_id: UUID, version_id: UUID, body: RevisionInput, db: Database, tenant: Tenant
) -> GraphValidation:
    return await service.validate_version(
        db, tenant, workflow_id, version_id, body.expected_revision
    )


@router.post("/{workflow_id}/versions/{version_id}/publish")
async def publish(
    workflow_id: UUID,
    version_id: UUID,
    body: RevisionInput,
    request: Request,
    db: Database,
    user: CurrentUser,
    tenant: Tenant,
) -> VersionDetail:
    return await service.publish(
        db, tenant, user, workflow_id, version_id, body.expected_revision, request.state.request_id
    )
