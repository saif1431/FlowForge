from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="ck_users_email_lower"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')", name="ck_auth_token_purpose"
        ),
        Index("ix_auth_tokens_user_purpose", "user_id", "purpose"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_events_org_created", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id"))
    resource_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    request_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        UniqueConstraint("organization_id", "id", name="uq_membership_org_id"),
        Index("ix_memberships_user_org", "user_id", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code"), default="member", server_default="member"
    )


class Role(Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))


class Permission(Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_code: Mapped[str] = mapped_column(ForeignKey("roles.code"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code"), primary_key=True)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_team_org_id"),
        UniqueConstraint("organization_id", "name", name="uq_team_org_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["teams.organization_id", "teams.id"],
            ondelete="CASCADE",
            name="fk_team_member_team",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_team_member_membership",
        ),
        Index("ix_team_members_org_membership", "organization_id", "membership_id"),
    )

    organization_id: Mapped[UUID]
    team_id: Mapped[UUID] = mapped_column(primary_key=True)
    membership_id: Mapped[UUID] = mapped_column(primary_key=True)


class Invitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_invitation_email_lower"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'revoked', 'expired')",
            name="ck_invitation_status",
        ),
        Index("ix_invitations_org_created", "organization_id", "created_at"),
        Index("ix_invitations_email", "email"),
        Index(
            "uq_invitation_pending",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("organization_id", "id", name="uq_workflow_org_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "workflow_id"],
            ["workflows.organization_id", "workflows.id"],
            name="fk_version_workflow",
        ),
        UniqueConstraint("organization_id", "id", name="uq_version_org_id"),
        UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version_number"),
        CheckConstraint("version_number > 0 AND revision > 0", name="ck_version_numbers"),
        CheckConstraint(
            "(status = 'draft' AND published_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL)",
            name="ck_version_status",
        ),
        Index(
            "uq_workflow_draft",
            "workflow_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    workflow_id: Mapped[UUID]
    version_number: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="draft")
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "version_id"],
            ["workflow_versions.organization_id", "workflow_versions.id"],
            name="fk_node_version",
        ),
        UniqueConstraint("organization_id", "version_id", "id", name="uq_node_org_version_id"),
    )

    version_id: Mapped[UUID] = mapped_column(primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    position_x: Mapped[float]
    position_y: Mapped[float]


class WorkflowEdge(Base):
    __tablename__ = "workflow_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "version_id", "source"],
            ["workflow_nodes.organization_id", "workflow_nodes.version_id", "workflow_nodes.id"],
            name="fk_edge_source",
        ),
        ForeignKeyConstraint(
            ["organization_id", "version_id", "target"],
            ["workflow_nodes.organization_id", "workflow_nodes.version_id", "workflow_nodes.id"],
            name="fk_edge_target",
        ),
        UniqueConstraint("version_id", "source", "branch", name="uq_edge_source_branch"),
        Index("ix_edge_org_version_target", "organization_id", "version_id", "target"),
    )

    version_id: Mapped[UUID] = mapped_column(primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID]
    source: Mapped[UUID]
    target: Mapped[UUID]
    branch: Mapped[str] = mapped_column(String(16))
