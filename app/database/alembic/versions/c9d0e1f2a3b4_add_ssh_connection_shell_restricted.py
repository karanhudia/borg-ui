"""add ssh_connections.shell_restricted

Recorded by the connection test when the key authenticated but the remote
shell refused the probe command (forced-command Borg-only key or restricted
shell). Null until the next test runs.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ssh_connections",
        sa.Column("shell_restricted", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ssh_connections", "shell_restricted")
