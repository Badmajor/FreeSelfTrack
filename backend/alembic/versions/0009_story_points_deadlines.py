"""Add story points, deadlines, and completing statuses.

Revision ID: 0009_story_points_deadlines
Revises: 0008_task_chat
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_story_points_deadlines"
down_revision: str | None = "0008_task_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_statuses",
        sa.Column("is_completed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("tasks", sa.Column("story_points", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("due_date", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_tasks_story_points_fibonacci",
        "tasks",
        "story_points IS NULL OR story_points IN (1, 2, 3, 5, 8, 13, 21)",
    )
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])
    op.create_table(
        "deadline_notification_deliveries",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "due_date", "recipient_id"),
    )


def downgrade() -> None:
    op.drop_table("deadline_notification_deliveries")
    op.drop_index("ix_tasks_due_date", table_name="tasks")
    op.drop_constraint("ck_tasks_story_points_fibonacci", "tasks", type_="check")
    op.drop_column("tasks", "due_date")
    op.drop_column("tasks", "story_points")
    op.drop_column("project_statuses", "is_completed")
