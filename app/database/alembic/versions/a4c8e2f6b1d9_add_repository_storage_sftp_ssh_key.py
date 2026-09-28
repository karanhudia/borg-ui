"""add an optional SFTP key for SSH cloud mirrors

Some hosts (BorgBase) restrict a key to either borg serve or SFTP, so the
cloud mirror's SSHFS mount may need a different key than borg uses on the
same connection (issue #1062).

Revision ID: a4c8e2f6b1d9
Revises: a4b5c6d7e8f9
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "a4c8e2f6b1d9"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repository_storage") as batch_op:
        batch_op.add_column(
            sa.Column(
                "sftp_ssh_key_id",
                sa.Integer(),
                sa.ForeignKey("ssh_keys.id", ondelete="SET NULL"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("repository_storage") as batch_op:
        batch_op.drop_column("sftp_ssh_key_id")
