"""add the operations runner lease

A replacement server process can start while the old one is still shutting
down; the lease decides which of the two runs operations (#1166).

Revision ID: e1a2b3c4d5f6
Revises: 5c7267e7aa2c
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa

revision = "e1a2b3c4d5f6"
down_revision = "5c7267e7aa2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_runner_lease",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("holder", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("operations_runner_lease")
