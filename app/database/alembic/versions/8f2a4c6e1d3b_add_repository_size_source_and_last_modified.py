"""add repository size source and borg last_modified

Revision ID: 8f2a4c6e1d3b
Revises: 7de0064b0d99
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa

revision = "8f2a4c6e1d3b"
down_revision = "7de0064b0d99"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic does not run SQLite DDL in a transaction: a boot killed after
    # the ALTER but before the version bump keeps the column, and re-running
    # this revision must not fail on the duplicate. Self-contained on purpose.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("repositories")
    }
    missing = [
        column
        for column in (
            sa.Column("total_size_source", sa.String(), nullable=True),
            sa.Column("borg_last_modified", sa.DateTime(), nullable=True),
        )
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("repositories") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("borg_last_modified")
        batch.drop_column("total_size_source")
