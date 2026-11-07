"""add prune_comparisons.verdicts and the archive-set fingerprint

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

from app.database.alembic_columns import add_missing_columns

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_missing_columns(
        "prune_comparisons",
        sa.Column("verdicts", sa.JSON(), nullable=True),
        sa.Column("archive_max_id", sa.Integer(), nullable=True),
        sa.Column("archive_seen_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("prune_comparisons") as batch:
        batch.drop_column("archive_seen_at")
        batch.drop_column("archive_max_id")
        batch.drop_column("verdicts")
