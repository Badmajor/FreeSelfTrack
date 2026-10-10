"""Invalidate legacy registration/reset requests without changing audit history.

Revision ID: 0022_disable_public_auth
Revises: 0021_remove_ownership
"""

from alembic import op

revision = "0022_disable_public_auth"
down_revision = "0021_remove_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM pending_registrations")
    op.execute("DELETE FROM password_resets")


def downgrade() -> None:
    # Expired/invalidated credentials must never be reconstructed on downgrade.
    pass
