"""add agent scripts to repository hooks

Revision ID: c4e532c20d7b
Revises: c8e1f4a7b2d9
Create Date: 2026-10-08

An agent repository's own pre/post-backup hooks are scripts its agent
publishes, named, the way plan hooks name them (#1386): a hook row holds
either a library script (`script_id`) or an agent script
(`agent_script_name`), so `script_id` becomes nullable. On SQLite the batch
rebuild keeps the rows, the indexes and the table's AUTOINCREMENT.

The downgrade deletes the agent-script hooks first: the older schema has no
place for them, and its `script_id` is NOT NULL again.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e532c20d7b"
down_revision = "c8e1f4a7b2d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table(
        "repository_scripts", table_kwargs={"sqlite_autoincrement": True}
    ) as batch:
        batch.add_column(
            sa.Column("agent_script_name", sa.String(length=255), nullable=True)
        )
        batch.alter_column("script_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM repository_scripts WHERE script_id IS NULL"))
    with op.batch_alter_table(
        "repository_scripts", table_kwargs={"sqlite_autoincrement": True}
    ) as batch:
        batch.alter_column("script_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("agent_script_name")
