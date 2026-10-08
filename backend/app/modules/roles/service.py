from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Role, RolePermission, User
from app.modules.organizations import repository as repo
from app.modules.organizations.service import audit
from app.modules.roles.authorization import manage_member, permissions, require
from app.modules.roles.schemas import AccessOutput, RoleList, RoleOutput


async def access(db: AsyncSession, tenant: repo.TenantContext) -> AccessOutput:
    result = AccessOutput(
        role_code=tenant.membership.role_code, permissions=await permissions(db, tenant)
    )
    await db.commit()
    return result


async def catalog(db: AsyncSession, tenant: repo.TenantContext) -> RoleList:
    await require(db, tenant, "directory:read")
    roles = list(await db.scalars(select(Role).order_by(Role.code)))
    mappings = list(await db.scalars(select(RolePermission)))
    result = RoleList(
        items=[
            RoleOutput(
                code=role.code,
                name=role.name,
                permissions=sorted(
                    row.permission_code for row in mappings if row.role_code == role.code
                ),
            )
            for role in roles
        ]
    )
    await db.commit()
    return result


async def assign(
    db: AsyncSession,
    tenant: repo.TenantContext,
    user: User,
    member_id: UUID,
    role_code: str,
    request_id: str,
) -> None:
    member = await repo.membership(db, tenant, member_id)
    await manage_member(db, tenant, member, "role:assign", role_code)
    if member.role_code != role_code:
        previous = member.role_code
        member.role_code = role_code
        audit(
            db,
            user,
            tenant.id,
            "membership.role_changed",
            request_id,
            member.id,
            {"previous_role": previous, "role": role_code},
        )
    await db.commit()
