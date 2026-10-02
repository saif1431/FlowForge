"""Explicit tenant scope is required for every tenant-owned resource lookup."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Invitation, Membership, Organization
from app.modules.auth.errors import AuthError


def missing() -> AuthError:
    return AuthError(404, "NOT_FOUND", "Organization or resource not found.")


@dataclass(frozen=True)
class TenantContext:
    organization: Organization
    membership: Membership

    @property
    def id(self) -> UUID:
        return self.organization.id


async def resolve(db: AsyncSession, org_id: UUID, user_id: UUID) -> TenantContext:
    # The org lock serializes membership revocation with authorized tenant operations.
    org = await db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    if org is None:
        raise missing()
    member = await db.scalar(
        select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
            Membership.revoked_at.is_(None),
        )
    )
    if member is None:
        raise missing()
    return TenantContext(org, member)


async def membership(db: AsyncSession, tenant: TenantContext, resource_id: UUID) -> Membership:
    row = await db.scalar(
        select(Membership).where(
            Membership.organization_id == tenant.id,
            Membership.id == resource_id,
            Membership.revoked_at.is_(None),
        )
    )
    if row is None:
        raise missing()
    return row


async def invitation(db: AsyncSession, tenant: TenantContext, resource_id: UUID) -> Invitation:
    row = await db.scalar(
        select(Invitation).where(
            Invitation.organization_id == tenant.id,
            Invitation.id == resource_id,
        )
    )
    if row is None:
        raise missing()
    return row
