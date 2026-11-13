"""add agent machine timezone

Revision ID: b9d2c5e7f1a4
Revises: c7e4f8a1d2b3
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "b9d2c5e7f1a4"
down_revision = "c7e4f8a1d2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic does not run SQLite DDL in a transaction: a boot killed after
    # the ALTER but before the version bump keeps the column, and re-running
    # this revision must not fail on the duplicate. Self-contained on purpose.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("agent_machines")
    }
    missing = [
        column
        for column in (sa.Column("timezone", sa.String(), nullable=True),)
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("agent_machines") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("agent_machines") as batch_op:
        batch_op.drop_column("timezone")
