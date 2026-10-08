"""Permission grants plus resource policies, under the tenant transaction lock."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Membership, RolePermission
from app.modules.auth.errors import AuthError
from app.modules.organizations.repository import TenantContext


async def permissions(db: AsyncSession, tenant: TenantContext) -> list[str]:
    return list(
        await db.scalars(
            select(RolePermission.permission_code)
            .where(RolePermission.role_code == tenant.membership.role_code)
            .order_by(RolePermission.permission_code)
        )
    )


async def require(db: AsyncSession, tenant: TenantContext, permission: str) -> None:
    grant = await db.scalar(
        select(RolePermission.permission_code).where(
            RolePermission.role_code == tenant.membership.role_code,
            RolePermission.permission_code == permission,
        )
    )
    if grant is None:
        raise AuthError(403, "FORBIDDEN", "You do not have permission to perform this action.")


async def manage_member(
    db: AsyncSession,
    tenant: TenantContext,
    target: Membership,
    permission: str,
    new_role: str | None = None,
) -> None:
    if target.user_id == tenant.organization.owner_user_id:
        raise AuthError(
            409, "OWNER_REQUIRED", "The organization owner cannot be changed or removed."
        )
    await require(db, tenant, permission)
    if target.role_code == "admin" or new_role == "admin":
        await require(db, tenant, "role:assign_admin")
    if target.id == tenant.membership.id:
        raise AuthError(403, "FORBIDDEN", "You cannot change your own role.")
