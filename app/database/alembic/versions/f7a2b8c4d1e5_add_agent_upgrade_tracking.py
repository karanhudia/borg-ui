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
    ("desired_agent_version", sa.String()),
    ("desired_borg_version", sa.String()),
    ("upgrade_state", sa.String()),
    ("upgrade_requested_at", sa.DateTime()),
    ("upgrade_target_version", sa.String()),
    ("upgrade_error", sa.Text()),
)


def upgrade() -> None:
    """Add nullable agent upgrade tracking columns to ``agent_machines``."""
    with op.batch_alter_table("agent_machines") as batch_op:
        for name, column_type in _COLUMNS:
            batch_op.add_column(sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    """Remove the agent upgrade tracking columns from ``agent_machines``."""
    with op.batch_alter_table("agent_machines") as batch_op:
        for name, _ in _COLUMNS:
            batch_op.drop_column(name)
