"""add agent machine timezone

Revision ID: b9d2c5e7f1a4
Revises: c7e4f8a1d2b3
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

from app.database.alembic_columns import add_missing_columns


revision = "b9d2c5e7f1a4"
down_revision = "c7e4f8a1d2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_missing_columns(
        "agent_machines",
        sa.Column("timezone", sa.String(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("agent_machines") as batch_op:
        batch_op.drop_column("timezone")
