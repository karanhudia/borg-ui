"""add repository_size_samples

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repository_size_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("measured_at", sa.DateTime(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_repository_size_samples_repository_id",
        "repository_size_samples",
        ["repository_id"],
    )
    op.create_index(
        "ix_repository_size_samples_measured_at",
        "repository_size_samples",
        ["measured_at"],
    )
    # The size each repository holds today is the first sample, so the
    # growth chart has a point to start from before the next measurement.
    op.execute(
        sa.text(
            "INSERT INTO repository_size_samples "
            "(repository_id, measured_at, size_bytes, source) "
            "SELECT id, COALESCE(total_size_measured_at, CURRENT_TIMESTAMP), "
            "total_size_bytes, total_size_source "
            "FROM repositories WHERE total_size_bytes IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_repository_size_samples_measured_at", table_name="repository_size_samples"
    )
    op.drop_index(
        "ix_repository_size_samples_repository_id", table_name="repository_size_samples"
    )
    op.drop_table("repository_size_samples")
