"""add immutable project task slugs and project sequence counters

Revision ID: 0007_task_slugs
Revises: 0006_profiles_task_history
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_task_slugs"
down_revision = "0006_profiles_task_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "project_task_sequences",
        sa.Column("project_id", uuid, nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.add_column("tasks", sa.Column("slug", sa.String(length=80), nullable=True))
    op.add_column("tasks", sa.Column("sequence_number", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id, project_id,
                       row_number() OVER (PARTITION BY project_id ORDER BY created_at, id) AS number
                FROM tasks
            )
            UPDATE tasks AS t
            SET sequence_number = ranked.number,
                slug = LEFT(
                    COALESCE(
                        NULLIF(REGEXP_REPLACE(UPPER(p.name), '[^A-Z0-9]+', '', 'g'), ''),
                        'TASK'
                    ),
                    40
                ) || '-' || ranked.number
            FROM ranked
            JOIN projects AS p ON p.id = ranked.project_id
            WHERE t.id = ranked.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO project_task_sequences (project_id, next_number)
            SELECT p.id, COALESCE(MAX(t.sequence_number), 0) + 1
            FROM projects AS p
            LEFT JOIN tasks AS t ON t.project_id = p.id
            GROUP BY p.id
            """
        )
    )
    op.alter_column("tasks", "slug", nullable=False)
    op.alter_column("tasks", "sequence_number", nullable=False)
    op.create_unique_constraint("uq_tasks_project_slug", "tasks", ["project_id", "slug"])
    op.create_unique_constraint(
        "uq_tasks_project_sequence", "tasks", ["project_id", "sequence_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_tasks_project_sequence", "tasks", type_="unique")
    op.drop_constraint("uq_tasks_project_slug", "tasks", type_="unique")
    op.drop_column("tasks", "sequence_number")
    op.drop_column("tasks", "slug")
    op.drop_table("project_task_sequences")
