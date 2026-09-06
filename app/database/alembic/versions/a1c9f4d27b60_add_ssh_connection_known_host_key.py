"""add ssh_connections.known_host_key

Holds the pinned host key (known_hosts lines) that every SSH invocation for
that connection verifies against. Null for connections that predate host-key
verification; those pin the key they see on their next use.

Revision ID: a1c9f4d27b60
Revises: 7de0064b0d99
Create Date: 2026-09-05 18:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c9f4d27b60"
down_revision: Union[str, Sequence[str], None] = "7de0064b0d99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ssh_connections",
        sa.Column("known_host_key", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ssh_connections", "known_host_key")
