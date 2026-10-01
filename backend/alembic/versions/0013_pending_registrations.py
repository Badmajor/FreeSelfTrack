"""Durable email-confirmation requests and SMTP delivery state."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_pending_registrations"
down_revision: str | None = "0012_task_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_pending_registrations_expires_at", "pending_registrations", ["expires_at"])
    op.create_index(
        "ix_pending_registrations_next_attempt_at", "pending_registrations", ["next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_table("pending_registrations")
