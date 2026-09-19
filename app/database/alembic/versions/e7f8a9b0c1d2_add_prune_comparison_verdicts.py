"""add prune_comparisons.verdicts

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.add_column(sa.Column("verdicts", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.drop_column("verdicts")
