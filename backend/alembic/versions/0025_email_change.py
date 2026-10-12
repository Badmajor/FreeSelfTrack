"""Latest user email confirmation and SMTP outbox.

Revision ID: 0025_email_change
Revises: 0024_archive_lifecycle
"""

import sqlalchemy as sa

from alembic import op

revision = "0025_email_change"
down_revision = "0024_archive_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_change_requests",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("new_email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    for column in ("expires_at", "next_attempt_at"):
        op.create_index(f"ix_email_change_requests_{column}", "email_change_requests", [column])


def downgrade() -> None:
    # Pending confirmations are intentionally invalidated on rollback.
    op.drop_table("email_change_requests")
