"""add operation wipe and rclone extension tables

Revision ID: e5f6a7b8c9d0
Revises: c3d5e7f9a1b2
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_wipe_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("phase", sa.String(), nullable=True),
        sa.Column("archive_count", sa.Integer(), nullable=True),
        sa.Column("archive_fingerprint", sa.String(), nullable=True),
        sa.Column("archive_manifest_json", sa.Text(), nullable=True),
        sa.Column("dry_run_output", sa.Text(), nullable=True),
        sa.Column("blocking_reason", sa.String(), nullable=True),
        sa.Column("protected_archives_json", sa.Text(), nullable=True),
        sa.Column(
            "run_compact", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "confirmed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "operation_rclone_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("direction", sa.String(), nullable=True),
        sa.Column("operation", sa.String(), nullable=False, server_default="sync"),
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),
        sa.Column("bytes_transferred", sa.BigInteger(), nullable=True),
        sa.Column("files_transferred", sa.Integer(), nullable=True),
        sa.Column("log_text", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("operation_rclone_details")
    op.drop_table("operation_wipe_details")
