"""Contract only after verified object transfer; no network I/O in migrations."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_remove_attachment_bytes"
down_revision: str | None = "0015_attachment_objects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM attachments WHERE object_key IS NULL OR sha256 IS NULL")
    ):
        raise RuntimeError(
            "Run attachment migrate at revision 0015_attachment_objects before upgrading to head"
        )
    op.drop_column("attachments", "content")


def downgrade() -> None:
    # Byte recovery requires a coordinated backup/object export; never fabricate bytes.
    op.add_column("attachments", sa.Column("content", sa.LargeBinary(), nullable=True))
