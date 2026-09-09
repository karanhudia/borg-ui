"""add operation restore extension table

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "f7a2b8c4d1e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_restore_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("archive", sa.String(), nullable=True),
        sa.Column("destination", sa.String(), nullable=True),
        sa.Column(
            "destination_type",
            sa.String(length=50),
            nullable=True,
            server_default="local",
        ),
        sa.Column(
            "destination_connection_id",
            sa.Integer(),
            sa.ForeignKey("ssh_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("temp_extraction_path", sa.String(length=255), nullable=True),
        sa.Column("destination_hostname", sa.String(length=255), nullable=True),
        sa.Column(
            "repository_type",
            sa.String(length=50),
            nullable=True,
            server_default="local",
        ),
        sa.Column("original_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("restored_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("restore_speed", sa.Float(), nullable=True, server_default="0"),
        sa.Column("nfiles", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("current_file", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("operation_restore_details")
