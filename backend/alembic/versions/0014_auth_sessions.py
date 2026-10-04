"""Revocable sessions, refresh families and durable password reset delivery."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_auth_sessions"
down_revision: str | None = "0013_pending_registrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "refresh_credentials",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_refresh_credentials_session_id", "refresh_credentials", ["session_id"])
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    for column in ("user_id", "expires_at", "next_attempt_at"):
        op.create_index(f"ix_password_resets_{column}", "password_resets", [column])


def downgrade() -> None:
    op.drop_table("password_resets")
    op.drop_table("refresh_credentials")
    op.drop_table("auth_sessions")
