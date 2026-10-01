"""Ensure every project has an active completing status.

Revision ID: 0011_required_completing_status
Revises: 0010_task_priority
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_required_completing_status"
down_revision: str | None = "0010_task_priority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH projects_without_completion AS (
            SELECT p.id
            FROM projects AS p
            WHERE NOT EXISTS (
                SELECT 1
                FROM project_statuses AS completed
                WHERE completed.project_id = p.id
                  AND completed.is_active IS TRUE
                  AND completed.is_completed IS TRUE
            )
        ),
        selected_status AS (
            SELECT DISTINCT ON (status.project_id) status.id
            FROM project_statuses AS status
            JOIN projects_without_completion AS project
              ON project.id = status.project_id
            WHERE status.is_active IS TRUE
            ORDER BY
                status.project_id,
                CASE WHEN status.name = 'Done' THEN 0 ELSE 1 END,
                status.position,
                status.id
        )
        UPDATE project_statuses
        SET is_completed = TRUE
        WHERE id IN (SELECT id FROM selected_status)
        """
    )


def downgrade() -> None:
    # Backfilled values may have been edited later and cannot be identified safely.
    pass
