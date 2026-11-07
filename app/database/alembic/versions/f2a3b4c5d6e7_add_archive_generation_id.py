"""Add an archive row identity independent of reusable IDs and wall time.

Revision ID: f2a3b4c5d6e7
Revises: a9b8c7d6e5f4
Create Date: 2026-09-12

Existing rows remain NULL until their next listing initializes identities.
Old merge results without an identity cannot delete rows.
"""

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic does not run SQLite DDL in a transaction: a boot killed after
    # the ALTER but before the version bump keeps the column, and re-running
    # this revision must not fail on the duplicate. Self-contained on purpose.
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("archives")}
    missing = [
        column
        for column in (sa.Column("generation_id", sa.String(36), nullable=True),)
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("archives") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    op.drop_column("archives", "generation_id")
