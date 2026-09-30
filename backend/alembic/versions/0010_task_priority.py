"""Add optional task priority.

Revision ID: 0010_task_priority
Revises: 0009_story_points_deadlines
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_task_priority"
down_revision: str | None = "0009_story_points_deadlines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("priority", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        "ck_tasks_priority",
        "tasks",
        "priority IS NULL OR priority IN ('low', 'normal', 'major', 'critical')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tasks_priority", "tasks", type_="check")
    op.drop_column("tasks", "priority")
