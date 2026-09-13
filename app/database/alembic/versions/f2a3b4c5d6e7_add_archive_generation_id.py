"""Add an archive row identity independent of reusable IDs and wall time.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-12

Existing rows remain NULL until their next listing initializes identities.
Old merge results without an identity cannot delete rows.
"""

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("archives", sa.Column("generation_id", sa.String(36), nullable=True))


def downgrade() -> None:
    op.drop_column("archives", "generation_id")
