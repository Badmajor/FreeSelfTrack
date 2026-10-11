"""Organization and project descriptions.

Revision ID: 0023_resource_descriptions
Revises: 0022_disable_public_auth
"""

import sqlalchemy as sa

from alembic import op

revision = "0023_resource_descriptions"
down_revision = "0022_disable_public_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "description")
    op.drop_column("organizations", "description")
