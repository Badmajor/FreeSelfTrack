"""Expand membership roles and backfill legacy ownership without reviving grants."""

import sqlalchemy as sa

from alembic import op

revision = "0020_administration_roles"
down_revision = "0019_administrative_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("is_system_admin", "must_change_password"):
        op.add_column(
            "users", sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # Configuration identifiers have no email-format/length policy.
    op.alter_column("users", "email", type_=sa.Text(), existing_type=sa.String(320))
    for scope in ("organization", "project"):
        table = f"{scope}_members"
        op.add_column(
            table, sa.Column("role", sa.String(16), nullable=False, server_default="member")
        )
        op.add_column(
            table, sa.Column("state", sa.String(16), nullable=False, server_default="active")
        )
        op.create_check_constraint(
            f"ck_{scope}_members_role", table, "role IN ('member', 'manager')"
        )
        op.create_check_constraint(
            f"ck_{scope}_members_state", table, "state IN ('active', 'archived', 'revoked')"
        )
        op.alter_column(f"{scope}s", "owner_id", nullable=True)
        op.execute(f"""
            INSERT INTO {table} ({scope}_id, user_id, role, state)
            SELECT id, owner_id, 'manager', 'revoked' FROM {scope}s WHERE owner_id IS NOT NULL
            ON CONFLICT ({scope}_id, user_id) DO UPDATE SET role = 'manager'
        """)
    # A known project owner requires organizational participation, but not the OM role.
    op.execute("""
        INSERT INTO organization_members (organization_id, user_id, role, state)
        SELECT DISTINCT organization_id, owner_id, 'member', 'revoked' FROM projects
        WHERE owner_id IS NOT NULL
        ON CONFLICT (organization_id, user_id) DO NOTHING
    """)
    op.execute("""
        UPDATE organization_members m SET state = CASE
            WHEN NOT u.is_active THEN 'revoked'
            WHEN o.deleted_at IS NOT NULL THEN 'archived' ELSE 'active' END
        FROM organizations o, users u WHERE m.organization_id = o.id AND m.user_id = u.id
    """)
    op.execute("""
        UPDATE project_members m SET state = CASE
            WHEN NOT u.is_active OR NOT EXISTS (
                SELECT 1 FROM organization_members om WHERE om.organization_id = p.organization_id
                AND om.user_id = m.user_id AND om.state != 'revoked'
            ) THEN 'revoked'
            WHEN p.deleted_at IS NOT NULL OR o.deleted_at IS NOT NULL THEN 'archived'
            ELSE 'active' END
        FROM projects p, organizations o, users u
        WHERE m.project_id = p.id AND o.id = p.organization_id AND m.user_id = u.id
    """)


def downgrade() -> None:
    # Losing role/state/system-account data is not a safe automatic rollback.
    raise RuntimeError("Restore the coordinated pre-transition backup; role downgrade is lossy")
