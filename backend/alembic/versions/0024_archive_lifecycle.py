"""Archive lifecycle and legacy cascade normalization.

Revision ID: 0024_archive_lifecycle
Revises: 0023_resource_descriptions
"""

import sqlalchemy as sa

from alembic import op

revision = "0024_archive_lifecycle"
down_revision = "0023_resource_descriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("organizations", "projects"):
        op.alter_column(table, "deleted_at", new_column_name="archived_at")
        op.execute(f"ALTER INDEX ix_{table}_deleted_at RENAME TO ix_{table}_archived_at")
    op.add_column("tasks", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tasks_archived_at", "tasks", ["archived_at"])
    op.execute("""UPDATE projects p SET archived_at = o.archived_at FROM organizations o
        WHERE p.organization_id = o.id AND p.archived_at IS NULL AND o.archived_at IS NOT NULL""")
    op.execute("""UPDATE tasks t SET archived_at = p.archived_at FROM projects p
        WHERE t.project_id = p.id AND p.archived_at IS NOT NULL""")
    op.execute("""UPDATE organization_members m SET state = 'archived'
        FROM organizations o WHERE m.organization_id = o.id
        AND m.state = 'active' AND o.archived_at IS NOT NULL""")
    op.execute("""UPDATE project_members m SET state = 'archived'
        FROM projects p WHERE m.project_id = p.id
        AND m.state = 'active' AND p.archived_at IS NOT NULL""")


def downgrade() -> None:
    raise RuntimeError(
        "Archive lifecycle cannot be downgraded without losing task archive state; "
        "use a forward fix or coordinated backup recovery"
    )
