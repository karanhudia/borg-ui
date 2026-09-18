"""add prune_comparisons

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prune_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("candidate", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("retention", sa.JSON(), nullable=True),
        sa.Column("kept_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "freed_at_least", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "partial_measure", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("archive_count_at", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("repository_id", "candidate", name="uq_prune_comparison"),
    )
    op.create_index(
        "ix_prune_comparisons_repository_id", "prune_comparisons", ["repository_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_prune_comparisons_repository_id", table_name="prune_comparisons")
    op.drop_table("prune_comparisons")
