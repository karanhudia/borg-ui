"""add repository index mode

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(
            sa.Column(
                "index_mode",
                sa.String(length=20),
                nullable=False,
                server_default="full",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("index_mode")
