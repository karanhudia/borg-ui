"""add system_settings.last_reconcile_tick_at

Revision ID: a7c3e9f1b5d2
Revises: e7f8a9b0c1d2
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa

revision = "a7c3e9f1b5d2"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic does not run SQLite DDL in a transaction: a boot killed after
    # the ALTER but before the version bump keeps the column, and re-running
    # this revision must not fail on the duplicate. Self-contained on purpose.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("system_settings")
    }
    missing = [
        column
        for column in (
            sa.Column("last_reconcile_tick_at", sa.DateTime(), nullable=True),
        )
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("system_settings") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("last_reconcile_tick_at")
