"""add operations (kind, started_at) index

The dashboard reads every operation of a kind started since a date; the
single-column kind index made that a scan of the whole kind.

Revision ID: c4d5e6f7a8b9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-17
"""

from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_operations_kind_started_at", "operations", ["kind", "started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_operations_kind_started_at", table_name="operations")
