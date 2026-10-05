"""Separate append-only administrative audit; no retrospective event backfill."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_administrative_audit"
down_revision: str | None = "0018_audit_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "administrative_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "(actor_kind = 'user' AND actor_id IS NOT NULL) OR "
            "(actor_kind = 'bootstrap' AND actor_id IS NULL)",
            name="ck_administrative_audit_actor",
        ),
        sa.CheckConstraint(
            "entity_type IN ('user', 'organization', 'project', 'task')",
            name="ck_administrative_audit_entity",
        ),
        sa.CheckConstraint(
            "action IN ('user_created', 'profile_updated', 'user_blocked', 'user_unblocked', "
            "'system_role_changed', 'created', 'updated', 'workflow_changed', 'member_added', "
            "'member_removed', 'member_role_changed', 'archived', 'restored')",
            name="ck_administrative_audit_action",
        ),
    )
    op.create_index(
        "ix_administrative_audit_entity_time",
        "administrative_audit_events",
        ["entity_type", "entity_id", "occurred_at", "id"],
    )
    # The shared rejecting function belongs to 0018; do not alter its existing protections.
    op.execute(
        "CREATE TRIGGER administrative_audit_immutable "
        "BEFORE UPDATE OR DELETE ON administrative_audit_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER administrative_audit_no_truncate "
        "BEFORE TRUNCATE ON administrative_audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation()"
    )
    op.execute(
        "ALTER TABLE administrative_audit_events "
        "ENABLE ALWAYS TRIGGER administrative_audit_immutable"
    )
    op.execute(
        "ALTER TABLE administrative_audit_events "
        "ENABLE ALWAYS TRIGGER administrative_audit_no_truncate"
    )


def downgrade() -> None:
    # Once producers exist, downgrade cannot silently destroy the new immutable journal.
    op.execute("LOCK TABLE administrative_audit_events IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM administrative_audit_events) THEN
                RAISE EXCEPTION 'Cannot downgrade a nonempty administrative audit'
                    USING HINT = 'Use the documented backup recovery procedure',
                    ERRCODE = '55000';
            END IF;
        END $$
    """)
    op.drop_table("administrative_audit_events")
