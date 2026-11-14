"""add maintenance concurrency settings

Revision ID: d3e8a1c6b2f9
Revises: f7a4417c5d4d
Create Date: 2026-11-14

`max_concurrent_maintenance` caps prune, compact and check operations the
runner starts (NULL or 0 is no cap, the old behaviour).
`maintenance_counts_toward_backup_limit` makes that maintenance take a
backup slot, and keeps a plan's slot until its post-backup steps finish.
"""

import sqlalchemy as sa
from alembic import op

revision = "d3e8a1c6b2f9"
down_revision = "f7a4417c5d4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Re-runnable: SQLite DDL is not transactional under Alembic.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("system_settings")
    }
    missing = [
        column
        for column in (
            sa.Column("max_concurrent_maintenance", sa.Integer(), nullable=True),
            sa.Column(
                "maintenance_counts_toward_backup_limit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("system_settings") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("maintenance_counts_toward_backup_limit")
        batch.drop_column("max_concurrent_maintenance")
