"""Append-only task history and security events."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_audit_integrity"
down_revision: str | None = "0017_attachment_scan_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_security_events_organization_created",
        "security_events",
        ["organization_id", "created_at", "id"],
    )
    op.execute("""
        CREATE FUNCTION reject_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Audit records are append-only' USING ERRCODE = '42501';
        END;
        $$
    """)
    for table in ("task_history", "security_events"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {table}_immutable")
        op.execute(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {table}_no_truncate")


def downgrade() -> None:
    for table in ("task_history", "security_events"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
    op.execute("DROP FUNCTION reject_audit_mutation()")
    op.drop_table("security_events")
