"""add task participants, watchers and notifications

Revision ID: 0005_task_participants
Revises: 0004_kanban_history_defaults
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_task_participants"
down_revision = "0004_kanban_history_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column("tasks", sa.Column("reporter_id", uuid, nullable=True))
    op.add_column("tasks", sa.Column("assignee_id", uuid, nullable=True))
    op.execute("UPDATE tasks SET reporter_id = created_by WHERE reporter_id IS NULL")
    op.alter_column("tasks", "reporter_id", nullable=False)
    op.create_foreign_key("fk_tasks_reporter_id_users", "tasks", "users", ["reporter_id"], ["id"])
    op.create_foreign_key("fk_tasks_assignee_id_users", "tasks", "users", ["assignee_id"], ["id"])
    op.create_index("ix_tasks_reporter_id", "tasks", ["reporter_id"])
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"])

    op.create_table(
        "task_watchers",
        sa.Column("task_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "user_id"),
    )
    op.create_index("ix_task_watchers_user_id", "task_watchers", ["user_id"])
    op.create_index("ix_task_watchers_created_at", "task_watchers", ["created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("recipient_id", uuid, nullable=False),
        sa.Column("task_id", uuid, nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("event_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_task_id", "notifications", ["task_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_id", "read_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_task_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_task_watchers_created_at", table_name="task_watchers")
    op.drop_index("ix_task_watchers_user_id", table_name="task_watchers")
    op.drop_table("task_watchers")
    op.drop_index("ix_tasks_assignee_id", table_name="tasks")
    op.drop_index("ix_tasks_reporter_id", table_name="tasks")
    op.drop_constraint("fk_tasks_assignee_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_reporter_id_users", "tasks", type_="foreignkey")
    op.drop_column("tasks", "assignee_id")
    op.drop_column("tasks", "reporter_id")
