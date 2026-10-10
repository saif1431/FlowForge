from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, Invitation, Membership, Organization, TeamMember, User
from app.modules.auth.errors import AuthError
from app.modules.auth.service import now
from app.modules.organizations import repository as repo
from app.modules.organizations.schemas import (
    InvitationList,
    InvitationOutput,
    MemberList,
    MemberOutput,
    OrganizationList,
    OrganizationOutput,
    PageInput,
)
from app.modules.roles.authorization import manage_member, require


def audit(
    db: AsyncSession,
    user: User,
    org_id: UUID,
    action: str,
    request_id: str,
    resource_id: UUID,
    details: dict[str, str] | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=user.id,
            organization_id=org_id,
            action=action,
            request_id=request_id,
            resource_id=resource_id,
            details=details,
        )
    )


async def create(db: AsyncSession, user: User, name: str, request_id: str) -> OrganizationOutput:
    org = Organization(name=name, owner_user_id=user.id)
    db.add(org)
    await db.flush()
    db.add(Membership(organization_id=org.id, user_id=user.id, role_code="owner"))
    audit(db, user, org.id, "organization.created", request_id, org.id)
    await db.commit()
    return OrganizationOutput.model_validate(org)


async def organizations(db: AsyncSession, user: User, page: PageInput) -> OrganizationList:
    query = (
        select(Organization)
        .join(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.revoked_at.is_(None),
        )
    )
    if page.cursor:
        query = query.where(Organization.id > page.cursor)
    rows = list(await db.scalars(query.order_by(Organization.id).limit(page.limit + 1)))
    await db.commit()
    return OrganizationList(
        items=[OrganizationOutput.model_validate(row) for row in rows[: page.limit]],
        next_cursor=rows[page.limit - 1].id if len(rows) > page.limit else None,
    )


async def rename(
    db: AsyncSession, tenant: repo.TenantContext, user: User, name: str, request_id: str
) -> OrganizationOutput:
    await require(db, tenant, "organization:update")
    tenant.organization.name = name
    audit(db, user, tenant.id, "organization.renamed", request_id, tenant.id)
    await db.commit()
    return OrganizationOutput.model_validate(tenant.organization)


async def members(db: AsyncSession, tenant: repo.TenantContext, page: PageInput) -> MemberList:
    await require(db, tenant, "directory:read")
    query = (
        select(Membership, User.email)
        .join(User)
        .where(
            Membership.organization_id == tenant.id,
            Membership.revoked_at.is_(None),
        )
    )
    if page.cursor:
        query = query.where(Membership.id > page.cursor)
    rows = list(await db.execute(query.order_by(Membership.id).limit(page.limit + 1)))
    result = MemberList(
        items=[
            MemberOutput(
                id=row.id,
                user_id=row.user_id,
                email=email,
                created_at=row.created_at,
                role_code=row.role_code,
            )
            for row, email in rows[: page.limit]
        ],
        next_cursor=rows[page.limit - 1][0].id if len(rows) > page.limit else None,
    )
    await db.commit()
    return result


async def remove_member(
    db: AsyncSession, tenant: repo.TenantContext, user: User, member_id: UUID, request_id: str
) -> None:
    member = await repo.membership(db, tenant, member_id)
    if member.user_id == tenant.organization.owner_user_id:
        raise AuthError(409, "OWNER_REQUIRED", "The organization owner cannot leave or be removed.")
    if member.user_id != user.id:
        await manage_member(db, tenant, member, "member:remove")
    else:
        await require(db, tenant, "membership:leave")
    await db.execute(
        delete(TeamMember).where(
            TeamMember.organization_id == tenant.id,
            TeamMember.membership_id == member.id,
        )
    )
    member.revoked_at = now()
    member.role_code = "member"
    audit(db, user, tenant.id, "membership.revoked", request_id, member.id)
    await db.commit()


def invitation_output(row: Invitation, org: Organization) -> InvitationOutput:
    status = "expired" if row.status == "pending" and row.expires_at <= now() else row.status
    return InvitationOutput(
        id=row.id,
        organization_id=row.organization_id,
        organization_name=org.name,
        email=row.email,
        status=status,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


async def invite(
    db: AsyncSession, tenant: repo.TenantContext, user: User, email: str, request_id: str
) -> InvitationOutput:
    await require(db, tenant, "invitation:manage")
    existing = await db.scalar(
        select(Membership.id)
        .join(User)
        .where(
            Membership.organization_id == tenant.id,
            Membership.revoked_at.is_(None),
            User.email == email,
        )
    )
    if existing:
        raise AuthError(409, "ALREADY_MEMBER", "This person is already a member.")
    await db.execute(
        update(Invitation)
        .where(
            Invitation.organization_id == tenant.id,
            Invitation.email == email,
            Invitation.status == "pending",
            Invitation.expires_at <= now(),
        )
        .values(status="expired")
    )
    pending = await db.scalar(
        select(Invitation).where(
            Invitation.organization_id == tenant.id,
            Invitation.email == email,
            Invitation.status == "pending",
        )
    )
    if pending:
        raise AuthError(409, "INVITATION_PENDING", "A pending invitation already exists.")
    row = Invitation(organization_id=tenant.id, email=email, expires_at=now() + timedelta(days=7))
    db.add(row)
    await db.flush()
    audit(db, user, tenant.id, "invitation.created", request_id, row.id)
    await db.commit()
    return invitation_output(row, tenant.organization)


async def invitations(
    db: AsyncSession, user: User, page: PageInput, tenant: repo.TenantContext | None = None
) -> InvitationList:
    query = select(Invitation, Organization).join(Organization)
    if tenant is None:
        # Explicit identity scope for recipients who are not members yet.
        query = query.where(Invitation.email == user.email)
    else:
        await require(db, tenant, "invitation:manage")
        query = query.where(Invitation.organization_id == tenant.id)
    if page.cursor:
        query = query.where(Invitation.id > page.cursor)
    rows = list(await db.execute(query.order_by(Invitation.id).limit(page.limit + 1)))
    result = InvitationList(
        items=[invitation_output(row, org) for row, org in rows[: page.limit]],
        next_cursor=rows[page.limit - 1][0].id if len(rows) > page.limit else None,
    )
    await db.commit()
    return result


def pending(row: Invitation) -> None:
    if row.status != "pending" or row.expires_at <= now():
        raise AuthError(409, "INVITATION_CLOSED", "This invitation is no longer pending.")


async def manage_invitation(
    db: AsyncSession,
    tenant: repo.TenantContext,
    user: User,
    invitation_id: UUID,
    action: Literal["revoke", "renew"],
    request_id: str,
) -> InvitationOutput:
    await require(db, tenant, "invitation:manage")
    row = await repo.invitation(db, tenant, invitation_id)
    pending(row)
    if action == "revoke":
        row.status = "revoked"
    else:
        row.expires_at = now() + timedelta(days=7)
    audit(db, user, tenant.id, f"invitation.{action}", request_id, row.id)
    await db.commit()
    return invitation_output(row, tenant.organization)


async def respond(
    db: AsyncSession,
    user: User,
    invitation_id: UUID,
    action: Literal["accept", "decline"],
    request_id: str,
) -> InvitationOutput:
    org_id = await db.scalar(
        select(Invitation.organization_id).where(
            Invitation.id == invitation_id,
            Invitation.email == user.email,
        )
    )
    if org_id is None:
        raise repo.missing()
    org = await db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    row = await db.scalar(
        select(Invitation)
        .where(
            Invitation.id == invitation_id,
            Invitation.organization_id == org_id,
            Invitation.email == user.email,
        )
        .execution_options(populate_existing=True)
    )
    if org is None or row is None:
        raise repo.missing()
    pending(row)
    if action == "accept":
        member = await db.scalar(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user.id,
            )
        )
        if member is None:
            member = Membership(organization_id=org_id, user_id=user.id)
            db.add(member)
        else:
            member.revoked_at = None
            member.role_code = "member"
        await db.flush()
        audit(db, user, org_id, "membership.joined", request_id, member.id)
        row.status = "accepted"
    else:
        row.status = "declined"
    audit(db, user, org_id, f"invitation.{row.status}", request_id, row.id)
    await db.commit()
    return invitation_output(row, org)
