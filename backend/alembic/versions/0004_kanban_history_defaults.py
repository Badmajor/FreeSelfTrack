"""add task history and default project statuses

Revision ID: 0004_kanban_history_defaults
Revises: 0003_membership_ownership
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_kanban_history_defaults"
down_revision = "0003_membership_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "task_history",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("task_id", uuid, nullable=False),
        sa.Column("changed_by", uuid, nullable=False),
        sa.Column("from_status_id", uuid, nullable=False),
        sa.Column("to_status_id", uuid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_status_id"], ["project_statuses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_status_id"], ["project_statuses.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_task_history_task_id", "task_history", ["task_id"])
    op.create_index("ix_task_history_created_at", "task_history", ["created_at"])
    op.create_index(
        "ix_task_history_task_created_at_id", "task_history", ["task_id", "created_at", "id"]
    )

    project_statuses = sa.table(
        "project_statuses",
        sa.column("id", uuid),
        sa.column("project_id", uuid),
        sa.column("name", sa.String),
        sa.column("position", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    projects_without_statuses = op.get_bind().execute(
        sa.text(
            "SELECT p.id FROM projects p WHERE NOT EXISTS "
            "(SELECT 1 FROM project_statuses s WHERE s.project_id = p.id)"
        )
    )
    rows = []
    for (project_id,) in projects_without_statuses:
        rows.extend(
            {
                "id": uuid4(),
                "project_id": project_id,
                "name": name,
                "position": position,
                "is_active": True,
            }
            for position, name in enumerate(("Backlog", "In Progress", "Done"))
        )
    if rows:
        op.bulk_insert(project_statuses, rows)


def downgrade() -> None:
    op.drop_index("ix_task_history_task_created_at_id", table_name="task_history")
    op.drop_index("ix_task_history_created_at", table_name="task_history")
    op.drop_index("ix_task_history_task_id", table_name="task_history")
    op.drop_table("task_history")
