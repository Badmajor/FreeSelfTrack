"""Index the pending attachment scan queue."""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_attachment_scan_index"
down_revision: str | None = "0016_remove_attachment_bytes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_attachments_state_id", "attachments", ["state", "id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_state_id", table_name="attachments")
