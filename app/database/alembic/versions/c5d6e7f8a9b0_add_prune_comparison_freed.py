"""add prune_comparisons.freed

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.add_column(sa.Column("freed", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.drop_column("freed")
