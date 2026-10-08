from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Membership,
    TeamMember,
    User,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowVersion,
)
from app.modules.auth.errors import AuthError
from app.modules.auth.service import now
from app.modules.organizations.repository import TenantContext
from app.modules.organizations.schemas import PageInput
from app.modules.organizations.service import audit
from app.modules.roles.authorization import require
from app.modules.workflows import repository as repo
from app.modules.workflows.schemas import (
    ApprovalConfig,
    GraphInput,
    GraphIssue,
    GraphValidation,
    VersionDetail,
    VersionList,
    VersionOutput,
    VersionPage,
    WorkflowCreated,
    WorkflowInput,
    WorkflowList,
    WorkflowOutput,
)
from app.modules.workflows.validation import structural_issues, validate_graph


def revision(row: WorkflowVersion, expected: int, editable: bool = False) -> None:
    if editable and row.status != "draft":
        raise AuthError(
            409, "VERSION_IMMUTABLE", "Published versions cannot be changed. Create a new draft."
        )
    if row.revision != expected:
        raise AuthError(
            409, "VERSION_CONFLICT", "This version changed. Reload it before saving or publishing."
        )


async def detail(db: AsyncSession, tenant: TenantContext, row: WorkflowVersion) -> VersionDetail:
    return VersionDetail(
        **VersionOutput.model_validate(row).model_dump(), graph=await repo.graph(db, tenant, row.id)
    )


async def write_graph(
    db: AsyncSession, tenant: TenantContext, version_id: UUID, graph: GraphInput
) -> None:
    # Structural errors cannot be saved because endpoint FKs and branch uniqueness must hold.
    issues = structural_issues(graph)
    if issues:
        raise AuthError(
            422,
            "GRAPH_INVALID",
            "Correct the graph references before saving.",
            {"issues": [issue.model_dump(mode="json") for issue in issues]},
        )
    await db.execute(
        delete(WorkflowEdge).where(
            WorkflowEdge.organization_id == tenant.id, WorkflowEdge.version_id == version_id
        )
    )
    await db.execute(
        delete(WorkflowNode).where(
            WorkflowNode.organization_id == tenant.id, WorkflowNode.version_id == version_id
        )
    )
    db.add_all(
        [
            WorkflowNode(
                organization_id=tenant.id,
                version_id=version_id,
                id=node.id,
                kind=node.kind,
                label=node.label,
                config=node.config,
                position_x=node.position.x,
                position_y=node.position.y,
            )
            for node in graph.nodes
        ]
    )
    await db.flush()
    db.add_all(
        [
            WorkflowEdge(
                organization_id=tenant.id,
                version_id=version_id,
                id=edge.id,
                source=edge.source,
                target=edge.target,
                branch=edge.branch,
            )
            for edge in graph.edges
        ]
    )
    await db.flush()


async def create(
    db: AsyncSession, tenant: TenantContext, user: User, body: WorkflowInput, request_id: str
) -> WorkflowCreated:
    await require(db, tenant, "workflow:create")
    workflow = Workflow(organization_id=tenant.id, name=body.name, description=body.description)
    db.add(workflow)
    await db.flush()
    draft = WorkflowVersion(organization_id=tenant.id, workflow_id=workflow.id, version_number=1)
    db.add(draft)
    await db.flush()
    audit(db, user, tenant.id, "workflow.created", request_id, workflow.id)
    audit(db, user, tenant.id, "workflow.draft_created", request_id, draft.id)
    result = WorkflowCreated(
        workflow=WorkflowOutput.model_validate(workflow), draft=await detail(db, tenant, draft)
    )
    await db.commit()
    return result


async def listing(db: AsyncSession, tenant: TenantContext, page: PageInput) -> WorkflowList:
    await require(db, tenant, "workflow:read")
    query = select(Workflow).where(Workflow.organization_id == tenant.id)
    if page.cursor:
        query = query.where(Workflow.id > page.cursor)
    rows = list(await db.scalars(query.order_by(Workflow.id).limit(page.limit + 1)))
    result = WorkflowList(
        items=[WorkflowOutput.model_validate(row) for row in rows[: page.limit]],
        next_cursor=rows[page.limit - 1].id if len(rows) > page.limit else None,
    )
    await db.commit()
    return result


async def get_workflow(
    db: AsyncSession, tenant: TenantContext, workflow_id: UUID
) -> WorkflowOutput:
    await require(db, tenant, "workflow:read")
    result = WorkflowOutput.model_validate(await repo.workflow(db, tenant, workflow_id))
    await db.commit()
    return result


async def versions(
    db: AsyncSession, tenant: TenantContext, workflow_id: UUID, page: VersionPage
) -> VersionList:
    await require(db, tenant, "workflow:read")
    await repo.workflow(db, tenant, workflow_id)
    query = select(WorkflowVersion).where(
        WorkflowVersion.organization_id == tenant.id,
        WorkflowVersion.workflow_id == workflow_id,
    )
    if page.cursor:
        query = query.where(WorkflowVersion.version_number < page.cursor)
    rows = list(
        await db.scalars(
            query.order_by(WorkflowVersion.version_number.desc()).limit(page.limit + 1)
        )
    )
    result = VersionList(
        items=[VersionOutput.model_validate(row) for row in rows[: page.limit]],
        next_cursor=rows[page.limit - 1].version_number if len(rows) > page.limit else None,
    )
    await db.commit()
    return result


async def get_version(
    db: AsyncSession, tenant: TenantContext, workflow_id: UUID, version_id: UUID
) -> VersionDetail:
    await require(db, tenant, "workflow:read")
    result = await detail(db, tenant, await repo.version(db, tenant, workflow_id, version_id))
    await db.commit()
    return result


async def save(
    db: AsyncSession,
    tenant: TenantContext,
    user: User,
    workflow_id: UUID,
    version_id: UUID,
    expected: int,
    graph: GraphInput,
    request_id: str,
) -> VersionDetail:
    await require(db, tenant, "workflow:edit")
    row = await repo.version(db, tenant, workflow_id, version_id)
    revision(row, expected, editable=True)
    await write_graph(db, tenant, row.id, graph)
    row.revision += 1
    audit(
        db,
        user,
        tenant.id,
        "workflow.draft_saved",
        request_id,
        row.id,
        {"revision": str(row.revision)},
    )
    result = await detail(db, tenant, row)
    await db.commit()
    return result


async def validation(db: AsyncSession, tenant: TenantContext, graph: GraphInput) -> GraphValidation:
    result = validate_graph(graph)
    for node in graph.nodes:
        if node.kind != "approval":
            continue
        assignee = ApprovalConfig.model_validate(node.config).assignee
        if assignee is None:
            continue
        query = select(Membership.id).where(
            Membership.organization_id == tenant.id,
            Membership.revoked_at.is_(None),
            Membership.role_code.in_(("owner", "admin", "approver")),
        )
        if assignee.kind == "member":
            query = query.where(Membership.id == assignee.id)
        else:
            query = query.join(TeamMember, TeamMember.membership_id == Membership.id).where(
                TeamMember.organization_id == tenant.id, TeamMember.team_id == assignee.id
            )
        if await db.scalar(query.limit(1)) is None:
            result.issues.append(
                GraphIssue(
                    code="APPROVER_UNAVAILABLE",
                    message="Select an eligible member or team in this organization. "
                    "Owners, Admins, and Approvers are eligible.",
                    node_id=node.id,
                )
            )
    result.valid = not result.issues
    return result


async def validate_version(
    db: AsyncSession, tenant: TenantContext, workflow_id: UUID, version_id: UUID, expected: int
) -> GraphValidation:
    await require(db, tenant, "workflow:read")
    row = await repo.version(db, tenant, workflow_id, version_id)
    revision(row, expected)
    result = await validation(db, tenant, await repo.graph(db, tenant, row.id))
    await db.commit()
    return result


async def publish(
    db: AsyncSession,
    tenant: TenantContext,
    user: User,
    workflow_id: UUID,
    version_id: UUID,
    expected: int,
    request_id: str,
) -> VersionDetail:
    await require(db, tenant, "workflow:publish")
    row = await repo.version(db, tenant, workflow_id, version_id)
    revision(row, expected, editable=True)
    graph = await repo.graph(db, tenant, row.id)
    report = await validation(db, tenant, graph)
    if not report.valid:
        raise AuthError(
            422,
            "GRAPH_INVALID",
            "Resolve validation errors before publishing.",
            {"issues": [issue.model_dump(mode="json") for issue in report.issues]},
        )
    row.status = "published"
    row.published_at = now()
    row.revision += 1
    audit(
        db,
        user,
        tenant.id,
        "workflow.published",
        request_id,
        row.id,
        {"version_number": str(row.version_number)},
    )
    result = VersionDetail(**VersionOutput.model_validate(row).model_dump(), graph=graph)
    await db.commit()
    return result


async def new_draft(
    db: AsyncSession,
    tenant: TenantContext,
    user: User,
    workflow_id: UUID,
    source_id: UUID | None,
    request_id: str,
) -> VersionDetail:
    await require(db, tenant, "workflow:edit")
    await repo.workflow(db, tenant, workflow_id)
    scope = (
        WorkflowVersion.organization_id == tenant.id,
        WorkflowVersion.workflow_id == workflow_id,
    )
    existing = await db.scalar(
        select(WorkflowVersion.id).where(*scope, WorkflowVersion.status == "draft")
    )
    if existing:
        raise AuthError(
            409, "DRAFT_EXISTS", "This workflow already has a draft. Open the existing draft."
        )
    source = (
        await repo.version(db, tenant, workflow_id, source_id)
        if source_id
        else await db.scalar(
            select(WorkflowVersion)
            .where(*scope, WorkflowVersion.status == "published")
            .order_by(WorkflowVersion.version_number.desc())
            .limit(1)
        )
    )
    if source is not None and source.status != "published":
        raise AuthError(409, "SOURCE_NOT_PUBLISHED", "Create drafts from a published version.")
    number = (
        await db.scalar(select(func.max(WorkflowVersion.version_number)).where(*scope)) or 0
    ) + 1
    row = WorkflowVersion(organization_id=tenant.id, workflow_id=workflow_id, version_number=number)
    db.add(row)
    await db.flush()
    if source is not None:
        await write_graph(db, tenant, row.id, await repo.graph(db, tenant, source.id))
    audit(
        db,
        user,
        tenant.id,
        "workflow.draft_created",
        request_id,
        row.id,
        {"source_version_id": str(source.id)} if source else None,
    )
    result = await detail(db, tenant, row)
    await db.commit()
    return result
