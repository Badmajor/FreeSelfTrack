"""Add canonical task links.

Revision ID: 0012_task_links
Revises: 0011_required_completing_status
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_task_links"
down_revision: str | None = "0011_required_completing_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_a_id", sa.Uuid(), nullable=False),
        sa.Column("task_b_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=16), nullable=False),
        sa.Column("blocking_task_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("task_a_id < task_b_id", name="ck_task_links_canonical_pair"),
        sa.CheckConstraint(
            "(relation_type = 'related' AND blocking_task_id IS NULL) OR "
            "(relation_type = 'blocks' AND blocking_task_id IN (task_a_id, task_b_id))",
            name="ck_task_links_type_direction",
        ),
        sa.ForeignKeyConstraint(["blocking_task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_a_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_b_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_a_id", "task_b_id", name="uq_task_links_pair"),
    )
    op.create_index("ix_task_links_task_a_id", "task_links", ["task_a_id"])
    op.create_index("ix_task_links_task_b_id", "task_links", ["task_b_id"])
    op.create_index("ix_tasks_slug_lookup", "tasks", [sa.text("lower(slug)")])


def downgrade() -> None:
    op.drop_index("ix_tasks_slug_lookup", table_name="tasks")
    op.drop_index("ix_task_links_task_b_id", table_name="task_links")
    op.drop_index("ix_task_links_task_a_id", table_name="task_links")
    op.drop_table("task_links")
