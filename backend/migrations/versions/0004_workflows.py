"""Workflow drafts, relational graphs and database-enforced published immutability."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_workflows"
down_revision = "0003_roles_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_workflow_org_id"),
    )
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["organization_id", "workflow_id"],
            ["workflows.organization_id", "workflows.id"],
            name="fk_version_workflow",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_version_org_id"),
        sa.UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version_number"),
        sa.CheckConstraint("version_number > 0 AND revision > 0", name="ck_version_numbers"),
        sa.CheckConstraint(
            "(status = 'draft' AND published_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL)",
            name="ck_version_status",
        ),
    )
    op.create_index(
        "uq_workflow_draft",
        "workflow_versions",
        ["workflow_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_table(
        "workflow_nodes",
        sa.Column("version_id", sa.Uuid(), primary_key=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "version_id"],
            ["workflow_versions.organization_id", "workflow_versions.id"],
            name="fk_node_version",
        ),
        sa.UniqueConstraint("organization_id", "version_id", "id", name="uq_node_org_version_id"),
    )
    op.create_table(
        "workflow_edges",
        sa.Column("version_id", sa.Uuid(), primary_key=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Uuid(), nullable=False),
        sa.Column("target", sa.Uuid(), nullable=False),
        sa.Column("branch", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "version_id", "source"],
            ["workflow_nodes.organization_id", "workflow_nodes.version_id", "workflow_nodes.id"],
            name="fk_edge_source",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "version_id", "target"],
            ["workflow_nodes.organization_id", "workflow_nodes.version_id", "workflow_nodes.id"],
            name="fk_edge_target",
        ),
        sa.UniqueConstraint("version_id", "source", "branch", name="uq_edge_source_branch"),
    )
    op.create_index(
        "ix_edge_org_version_target", "workflow_edges", ["organization_id", "version_id", "target"]
    )
    # Lock the parent version for child writes, so direct concurrent SQL cannot race publication.
    op.execute("""
        CREATE FUNCTION guard_workflow_graph() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                PERFORM 1 FROM workflow_versions
                WHERE id = OLD.version_id AND organization_id = OLD.organization_id
                FOR UPDATE;
                IF EXISTS (SELECT 1 FROM workflow_versions WHERE id = OLD.version_id
                           AND organization_id = OLD.organization_id AND status = 'published') THEN
                    RAISE EXCEPTION 'Published workflow versions are immutable'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            IF TG_OP <> 'DELETE' THEN
                PERFORM 1 FROM workflow_versions
                WHERE id = NEW.version_id AND organization_id = NEW.organization_id
                FOR UPDATE;
                IF EXISTS (SELECT 1 FROM workflow_versions WHERE id = NEW.version_id
                           AND organization_id = NEW.organization_id AND status = 'published') THEN
                    RAISE EXCEPTION 'Published workflow versions are immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            RETURN OLD;
        END;
        $$
    """)
    op.execute("""
        CREATE FUNCTION guard_published_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = 'published' THEN
                RAISE EXCEPTION 'Published workflow versions are immutable' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
    """)
    for table in ("workflow_nodes", "workflow_edges"):
        op.execute(
            f"CREATE TRIGGER immutable_graph BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION guard_workflow_graph()"
        )
    op.execute(
        "CREATE TRIGGER immutable_version BEFORE UPDATE OR DELETE ON workflow_versions "
        "FOR EACH ROW EXECUTE FUNCTION guard_published_version()"
    )
    permissions = sa.table("permissions", sa.column("code", sa.String()))
    mappings = sa.table(
        "role_permissions",
        sa.column("role_code", sa.String()),
        sa.column("permission_code", sa.String()),
    )
    op.bulk_insert(
        permissions,
        [{"code": f"workflow:{action}"} for action in ("read", "create", "edit", "publish")],
    )
    grants = {
        "read": ("owner", "admin", "designer", "approver", "member", "viewer"),
        "create": ("owner", "admin", "designer"),
        "edit": ("owner", "admin", "designer"),
        "publish": ("owner", "admin"),
    }
    op.bulk_insert(
        mappings,
        [
            {"role_code": role, "permission_code": f"workflow:{action}"}
            for action, roles in grants.items()
            for role in roles
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_code IN "
        "('workflow:read', 'workflow:create', 'workflow:edit', 'workflow:publish')"
    )
    op.execute(
        "DELETE FROM permissions WHERE code IN "
        "('workflow:read', 'workflow:create', 'workflow:edit', 'workflow:publish')"
    )
    op.drop_table("workflow_edges")
    op.drop_table("workflow_nodes")
    op.drop_table("workflow_versions")
    op.drop_table("workflows")
    op.execute("DROP FUNCTION guard_workflow_graph()")
    op.execute("DROP FUNCTION guard_published_version()")
