"""add repository size source and borg last_modified

Revision ID: 8f2a4c6e1d3b
Revises: 7de0064b0d99
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa

revision = "8f2a4c6e1d3b"
down_revision = "7de0064b0d99"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(sa.Column("total_size_source", sa.String(), nullable=True))
        batch.add_column(sa.Column("borg_last_modified", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("borg_last_modified")
        batch.drop_column("total_size_source")
