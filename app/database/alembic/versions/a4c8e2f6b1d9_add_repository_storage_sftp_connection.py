"""add an optional SFTP connection for SSH cloud mirrors

Some hosts (BorgBase) restrict a key to either borg serve or SFTP, so the
cloud mirror's SSHFS mount may need a different connection than borg uses
(issue #1062).

Revision ID: a4c8e2f6b1d9
Revises: f2b3c4d5e6a7
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "a4c8e2f6b1d9"
down_revision = "f2b3c4d5e6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repository_storage") as batch_op:
        batch_op.add_column(
            sa.Column(
                "sftp_connection_id",
                sa.Integer(),
                sa.ForeignKey("ssh_connections.id", ondelete="SET NULL"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("repository_storage") as batch_op:
        batch_op.drop_column("sftp_connection_id")
