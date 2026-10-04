"""Expand attachment metadata; preserve legacy bytes for offline transfer."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_attachment_objects"
down_revision: str | None = "0014_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("attachments", "content", existing_type=sa.LargeBinary(), nullable=True)
    op.add_column("attachments", sa.Column("position", sa.Integer()))
    # The old schema had no explicit order. Freeze its heap/insertion order per
    # comment at cutover; all subsequent publications persist their input order.
    op.execute(
        sa.text("""
        UPDATE attachments AS a SET position = ordered.position
        FROM (SELECT id, row_number() OVER (PARTITION BY comment_id ORDER BY ctid) - 1 AS position
              FROM attachments) AS ordered WHERE a.id = ordered.id
    """)
    )
    op.alter_column("attachments", "position", nullable=False)
    op.create_unique_constraint("uq_attachment_position", "attachments", ["comment_id", "position"])
    op.create_check_constraint(
        "ck_attachment_position", "attachments", "position >= 0 AND position < 5"
    )
    op.add_column("attachments", sa.Column("object_key", sa.String(100)))
    op.add_column("attachments", sa.Column("sha256", sa.String(64)))
    op.add_column(
        "attachments", sa.Column("state", sa.String(16), nullable=False, server_default="pending")
    )
    op.create_unique_constraint("uq_attachment_object_key", "attachments", ["object_key"])
    op.create_check_constraint(
        "ck_attachment_state", "attachments", "state IN ('pending', 'ready', 'failed', 'infected')"
    )
    op.create_check_constraint(
        "ck_attachment_size", "attachments", "size >= 0 AND size <= 26214400"
    )
    op.create_check_constraint(
        "ck_attachment_ready",
        "attachments",
        "state != 'ready' OR (object_key IS NOT NULL AND sha256 IS NOT NULL)",
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM attachments WHERE content IS NULL")):
        raise RuntimeError("Restore legacy bytes from a verified backup before downgrade")
    op.drop_constraint("uq_attachment_position", "attachments", type_="unique")
    op.drop_constraint("ck_attachment_position", "attachments", type_="check")
    op.drop_column("attachments", "position")
    for name in ("ck_attachment_ready", "ck_attachment_size", "ck_attachment_state"):
        op.drop_constraint(name, "attachments", type_="check")
    op.drop_constraint("uq_attachment_object_key", "attachments", type_="unique")
    for name in ("state", "sha256", "object_key"):
        op.drop_column("attachments", name)
    op.alter_column("attachments", "content", existing_type=sa.LargeBinary(), nullable=False)
