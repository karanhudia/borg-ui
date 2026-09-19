"""add prune_comparisons.lost_size

Revision ID: c5d6e7f8a9b0
Revises: d5e6f7a8b9c0
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.add_column(sa.Column("lost_size", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.drop_column("lost_size")
