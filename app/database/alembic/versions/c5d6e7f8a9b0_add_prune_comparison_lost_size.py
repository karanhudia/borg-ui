"""add prune_comparisons.lost_size

Revision ID: c5d6e7f8a9b0
Revises: d5e6f7a8b9c0
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic does not run SQLite DDL in a transaction: a boot killed after
    # the ALTER but before the version bump keeps the column, and re-running
    # this revision must not fail on the duplicate. Self-contained on purpose.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("prune_comparisons")
    }
    missing = [
        column
        for column in (sa.Column("lost_size", sa.BigInteger(), nullable=True),)
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("prune_comparisons") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.drop_column("lost_size")
