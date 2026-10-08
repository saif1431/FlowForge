from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workflow, WorkflowEdge, WorkflowNode, WorkflowVersion
from app.modules.organizations.repository import TenantContext, missing
from app.modules.workflows.schemas import GraphInput


async def workflow(db: AsyncSession, tenant: TenantContext, workflow_id: UUID) -> Workflow:
    row = await db.scalar(
        select(Workflow).where(Workflow.organization_id == tenant.id, Workflow.id == workflow_id)
    )
    if row is None:
        raise missing()
    return row


async def version(
    db: AsyncSession, tenant: TenantContext, workflow_id: UUID, version_id: UUID
) -> WorkflowVersion:
    row = await db.scalar(
        select(WorkflowVersion)
        .where(
            WorkflowVersion.organization_id == tenant.id,
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.id == version_id,
        )
        .with_for_update()
    )
    if row is None:
        raise missing()
    return row


async def graph(db: AsyncSession, tenant: TenantContext, version_id: UUID) -> GraphInput:
    nodes = list(
        await db.scalars(
            select(WorkflowNode)
            .where(WorkflowNode.organization_id == tenant.id, WorkflowNode.version_id == version_id)
            .order_by(WorkflowNode.id)
        )
    )
    edges = list(
        await db.scalars(
            select(WorkflowEdge)
            .where(WorkflowEdge.organization_id == tenant.id, WorkflowEdge.version_id == version_id)
            .order_by(WorkflowEdge.id)
        )
    )
    return GraphInput.model_validate(
        {
            "nodes": [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "label": row.label,
                    "config": row.config,
                    "position": {"x": row.position_x, "y": row.position_y},
                }
                for row in nodes
            ],
            "edges": [
                {"id": row.id, "source": row.source, "target": row.target, "branch": row.branch}
                for row in edges
            ],
        }
    )
