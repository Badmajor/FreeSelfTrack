"""create core task domain

Revision ID: 0001_core_task_domain
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_core_task_domain"
down_revision = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "organizations",
        sa.Column("id", uuid, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "organization_members",
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "user_id"),
    )
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])
    op.create_table(
        "projects",
        sa.Column("id", uuid, nullable=False),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_table(
        "project_members",
        sa.Column("project_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    op.create_table(
        "project_statuses",
        sa.Column("id", uuid, nullable=False),
        sa.Column("project_id", uuid, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "id", name="uq_project_statuses_project_id"),
        sa.UniqueConstraint("project_id", "position", name="uq_project_statuses_project_position"),
    )
    op.create_index("ix_project_statuses_project_id", "project_statuses", ["project_id"])
    op.create_table(
        "tasks",
        sa.Column("id", uuid, nullable=False),
        sa.Column("project_id", uuid, nullable=False),
        sa.Column("status_id", uuid, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", uuid, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "status_id"],
            ["project_statuses.project_id", "project_statuses.id"],
            name="fk_tasks_project_status_same_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_status_id", "tasks", ["status_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_status_id", table_name="tasks")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_project_statuses_project_id", table_name="project_statuses")
    op.drop_table("project_statuses")
    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_table("project_members")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_organization_members_user_id", table_name="organization_members")
    op.drop_table("organization_members")
    op.drop_table("organizations")
