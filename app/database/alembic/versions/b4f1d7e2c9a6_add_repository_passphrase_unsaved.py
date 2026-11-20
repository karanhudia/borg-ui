"""add repositories passphrase_unsaved

Revision ID: b4f1d7e2c9a6
Revises: a9e3c7b1d5f2
Create Date: 2026-11-20

Set when Borg UI generated a repository's passphrase over MCP and the user
has not confirmed saving it yet (spec 2026-11-14-mcp-server, 5.9).
"""

from alembic import op
import sqlalchemy as sa

revision = "b4f1d7e2c9a6"
down_revision = "a9e3c7b1d5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Re-runnable: SQLite DDL is not transactional under Alembic.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("repositories")
    }
    if "passphrase_unsaved" in existing:
        return
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(
            sa.Column(
                "passphrase_unsaved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("passphrase_unsaved")
