"""Contract legacy ownership after verifying every owner mapping was transferred."""

from alembic import op

revision = "0021_remove_ownership"
down_revision = "0020_administration_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for scope in ("organization", "project"):
        op.execute(f"""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM {scope}s s WHERE s.owner_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM {scope}_members m WHERE m.{scope}_id = s.id
                        AND m.user_id = s.owner_id AND m.role = 'manager'
                    )
                ) THEN RAISE EXCEPTION 'Owner backfill verification failed'; END IF;
            END $$
        """)
        op.drop_index(f"ix_{scope}s_owner_id", table_name=f"{scope}s")
        op.drop_constraint(f"fk_{scope}s_owner_id_users", f"{scope}s", type_="foreignkey")
        op.drop_column(f"{scope}s", "owner_id")


def downgrade() -> None:
    raise RuntimeError("Ownership cannot be reconstructed from zero or multiple managers")
