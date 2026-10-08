"""Fixed roles, permissions and tenant-constrained teams; preserve M1/M2 data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_roles_teams"
down_revision = "0002_organizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
    )
    permissions = op.create_table(
        "permissions",
        sa.Column("code", sa.String(64), primary_key=True),
    )
    mappings = op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(32), sa.ForeignKey("roles.code"), primary_key=True),
        sa.Column(
            "permission_code", sa.String(64), sa.ForeignKey("permissions.code"), primary_key=True
        ),
    )
    names = {
        "owner": "Owner",
        "admin": "Admin",
        "designer": "Designer",
        "approver": "Approver",
        "member": "Member",
        "viewer": "Viewer / Auditor",
    }
    directory = {"directory:read"}
    management = {
        "organization:update",
        "invitation:manage",
        "member:remove",
        "role:assign",
        "team:manage",
    }
    grants = {
        "owner": directory | management | {"role:assign_admin"},
        "admin": directory | management | {"membership:leave"},
        **{
            code: directory | {"membership:leave"}
            for code in ("designer", "approver", "member", "viewer")
        },
    }
    op.bulk_insert(roles, [{"code": code, "name": name} for code, name in names.items()])
    op.bulk_insert(permissions, [{"code": code} for code in sorted(set.union(*grants.values()))])
    op.bulk_insert(
        mappings,
        [
            {"role_code": role, "permission_code": permission}
            for role, codes in grants.items()
            for permission in sorted(codes)
        ],
    )
    op.add_column(
        "organization_memberships",
        sa.Column("role_code", sa.String(32), nullable=False, server_default="member"),
    )
    op.create_foreign_key(
        "fk_membership_role", "organization_memberships", "roles", ["role_code"], ["code"]
    )
    op.execute(
        "UPDATE organization_memberships AS m SET role_code = 'owner' "
        "FROM organizations AS o WHERE m.organization_id = o.id "
        "AND m.user_id = o.owner_user_id"
    )
    op.create_unique_constraint(
        "uq_membership_org_id", "organization_memberships", ["organization_id", "id"]
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_team_org_id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_team_org_name"),
    )
    op.create_table(
        "team_members",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), primary_key=True),
        sa.Column("membership_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["teams.organization_id", "teams.id"],
            ondelete="CASCADE",
            name="fk_team_member_team",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
            name="fk_team_member_membership",
        ),
    )
    op.create_index(
        "ix_team_members_org_membership", "team_members", ["organization_id", "membership_id"]
    )
    op.add_column("audit_events", sa.Column("details", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("audit_events", "details")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_constraint("uq_membership_org_id", "organization_memberships", type_="unique")
    op.drop_column("organization_memberships", "role_code")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
