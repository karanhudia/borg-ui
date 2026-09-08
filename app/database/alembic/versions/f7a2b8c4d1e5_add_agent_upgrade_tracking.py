"""add agent upgrade tracking columns

The columns landed in the model with the centralized agent upgrades work but
only ever got a legacy ladder file (129), which is frozen and no longer runs at
startup. Every Alembic-managed database is therefore missing them.

Revision ID: f7a2b8c4d1e5
Revises: e5f6a7b8c9d0
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa


revision = "f7a2b8c4d1e5"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("desired_agent_version", sa.String(), nullable=True),
    sa.Column("desired_borg_version", sa.String(), nullable=True),
    sa.Column("upgrade_state", sa.String(), nullable=True),
    sa.Column("upgrade_requested_at", sa.DateTime(), nullable=True),
    sa.Column("upgrade_target_version", sa.String(), nullable=True),
    sa.Column("upgrade_error", sa.Text(), nullable=True),
)


def upgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("agent_machines")
    }
    missing = [column for column in _COLUMNS if column.name not in existing]
    if not missing:
        return
    with op.batch_alter_table("agent_machines") as batch_op:
        for column in missing:
            batch_op.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("agent_machines") as batch_op:
        for column in _COLUMNS:
            batch_op.drop_column(column.name)
