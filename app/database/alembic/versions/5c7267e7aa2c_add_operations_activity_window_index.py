"""add operations index for the Activity window

The Activity list orders operations by coalesce(started_at, created_at) and
pages on the same expression; without an index on it every call scanned and
sorted the whole table.

Revision ID: 5c7267e7aa2c
Revises: d4e5f6a7b8c9
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa

revision = "5c7267e7aa2c"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_operations_activity_window",
        "operations",
        [sa.text("coalesce(started_at, created_at) DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_operations_activity_window", table_name="operations")
