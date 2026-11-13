"""add prune_comparisons.verdicts and the archive-set fingerprint

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
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
        for column in (
            sa.Column("verdicts", sa.JSON(), nullable=True),
            sa.Column("archive_max_id", sa.Integer(), nullable=True),
            sa.Column("archive_seen_at", sa.DateTime(), nullable=True),
        )
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("prune_comparisons") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.drop_column("archive_seen_at")
        batch.drop_column("archive_max_id")
        batch.drop_column("verdicts")
