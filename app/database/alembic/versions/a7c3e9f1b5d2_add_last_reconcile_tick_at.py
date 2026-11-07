"""add system_settings.last_reconcile_tick_at

Revision ID: a7c3e9f1b5d2
Revises: e7f8a9b0c1d2
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa

from app.database.alembic_columns import add_missing_columns

revision = "a7c3e9f1b5d2"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_missing_columns(
        "system_settings",
        sa.Column("last_reconcile_tick_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("last_reconcile_tick_at")
