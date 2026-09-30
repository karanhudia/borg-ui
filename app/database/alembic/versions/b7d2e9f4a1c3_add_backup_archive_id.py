"""record the archive id a backup created

A Borg 2 series shares one archive name, so a post-backup restore check
that picks the newest archive of the name can verify another plan's
backup. The id Borg reports for the archive `create` made is kept on the
backup's details row and the check targets it (issue #1232).

Revision ID: b7d2e9f4a1c3
Revises: a4c8e2f6b1d9
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "b7d2e9f4a1c3"
down_revision = "a4c8e2f6b1d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operation_backup_details") as batch_op:
        batch_op.add_column(sa.Column("archive_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("operation_backup_details") as batch_op:
        batch_op.drop_column("archive_id")
