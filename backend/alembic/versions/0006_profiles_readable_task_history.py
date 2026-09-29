"""add required user profiles and readable task history fields

Revision ID: 0006_profiles_readable_task_history
Revises: 0005_task_participants
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_profiles_task_history"
down_revision = "0005_task_participants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "user_profiles",
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute(
        "INSERT INTO user_profiles (user_id, first_name, last_name, created_at, updated_at) "
        "SELECT id, 'Unknown', 'User', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM users"
    )

    op.add_column(
        "task_history", sa.Column("event_type", sa.String(length=64), nullable=True)
    )
    op.add_column("task_history", sa.Column("field_name", sa.String(length=64), nullable=True))
    op.add_column("task_history", sa.Column("old_value", sa.Text(), nullable=True))
    op.add_column("task_history", sa.Column("new_value", sa.Text(), nullable=True))
    op.execute(
        "UPDATE task_history SET event_type = 'status_changed', field_name = 'status' "
        "WHERE event_type IS NULL"
    )
    op.alter_column("task_history", "event_type", nullable=False)
    op.alter_column("task_history", "from_status_id", nullable=True)
    op.alter_column("task_history", "to_status_id", nullable=True)


def downgrade() -> None:
    op.alter_column("task_history", "to_status_id", nullable=False)
    op.alter_column("task_history", "from_status_id", nullable=False)
    op.drop_column("task_history", "new_value")
    op.drop_column("task_history", "old_value")
    op.drop_column("task_history", "field_name")
    op.drop_column("task_history", "event_type")
    op.drop_table("user_profiles")
