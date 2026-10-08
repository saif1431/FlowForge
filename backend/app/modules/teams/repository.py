from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Team
from app.modules.organizations.repository import TenantContext, missing


async def team(db: AsyncSession, tenant: TenantContext, team_id: UUID) -> Team:
    row = await db.scalar(select(Team).where(Team.organization_id == tenant.id, Team.id == team_id))
    if row is None:
        raise missing()
    return row
