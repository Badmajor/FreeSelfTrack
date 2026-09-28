"""add membership ownership and soft deletion

Revision ID: 0003_membership_ownership
Revises: 0002_users
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_membership_ownership"
down_revision = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column("organizations", sa.Column("owner_id", uuid, nullable=True))
    op.add_column(
        "organizations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("projects", sa.Column("owner_id", uuid, nullable=True))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # Existing creators were automatically added as members by the previous service.
    op.execute(
        """
        UPDATE organizations AS organization
        SET owner_id = (
            SELECT member.user_id
            FROM organization_members AS member
            WHERE member.organization_id = organization.id
            ORDER BY member.user_id
            LIMIT 1
        )
        WHERE owner_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE projects AS project
        SET owner_id = (
            SELECT member.user_id
            FROM project_members AS member
            WHERE member.project_id = project.id
            ORDER BY member.user_id
            LIMIT 1
        )
        WHERE owner_id IS NULL
        """
    )

    op.alter_column("organizations", "owner_id", nullable=False)
    op.alter_column("projects", "owner_id", nullable=False)
    op.create_foreign_key(
        "fk_organizations_owner_id_users", "organizations", "users", ["owner_id"], ["id"]
    )
    op.create_foreign_key("fk_projects_owner_id_users", "projects", "users", ["owner_id"], ["id"])
    op.create_foreign_key(
        "fk_organization_members_user_id_users",
        "organization_members",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_project_members_user_id_users",
        "project_members",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_organizations_deleted_at", "organizations", ["deleted_at"])
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"])
    op.create_index("ix_organizations_owner_id", "organizations", ["owner_id"])
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_index("ix_organizations_owner_id", table_name="organizations")
    op.drop_index("ix_projects_deleted_at", table_name="projects")
    op.drop_index("ix_organizations_deleted_at", table_name="organizations")
    op.drop_constraint("fk_project_members_user_id_users", "project_members", type_="foreignkey")
    op.drop_constraint(
        "fk_organization_members_user_id_users", "organization_members", type_="foreignkey"
    )
    op.drop_constraint("fk_projects_owner_id_users", "projects", type_="foreignkey")
    op.drop_constraint("fk_organizations_owner_id_users", "organizations", type_="foreignkey")
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "owner_id")
    op.drop_column("organizations", "deleted_at")
    op.drop_column("organizations", "owner_id")
