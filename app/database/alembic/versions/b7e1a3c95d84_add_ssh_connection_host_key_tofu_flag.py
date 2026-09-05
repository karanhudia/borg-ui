"""add ssh_connections.host_key_trust_on_first_use

Marks the connections that existed before host-key verification did. Those pin
whatever key answers on their next use: they were already running with no
verification at all, so recording the current key is strictly better than the
status quo and does not break an install on upgrade.

Every connection created after this migration defaults to false and needs the
user to confirm the fingerprint before a key is pinned, which is the moment the
verification is actually worth something.

Revision ID: b7e1a3c95d84
Revises: a1c9f4d27b60
Create Date: 2026-09-05 19:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e1a3c95d84"
down_revision: Union[str, Sequence[str], None] = "a1c9f4d27b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ssh_connections",
        sa.Column("host_key_trust_on_first_use", sa.Boolean(), nullable=True),
    )
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            "UPDATE ssh_connections SET host_key_trust_on_first_use = :value "
            "WHERE known_host_key IS NULL"
        ),
        {"value": True},
    )
    print(
        f"✓ {result.rowcount} existing SSH connection(s) will pin their host key "
        "on next use"
    )


def downgrade() -> None:
    op.drop_column("ssh_connections", "host_key_trust_on_first_use")
