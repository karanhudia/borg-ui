"""add system_settings mcp_beta_enabled

Revision ID: a9e3c7b1d5f2
Revises: c8d2e5f1a3b7
Create Date: 2026-11-19

MCP stays behind a beta switch, off by default, until every phase of spec
2026-11-14-mcp-server is final.
"""

from alembic import op
import sqlalchemy as sa

revision = "a9e3c7b1d5f2"
down_revision = "c8d2e5f1a3b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Re-runnable: SQLite DDL is not transactional under Alembic.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("system_settings")
    }
    if "mcp_beta_enabled" in existing:
        return
    with op.batch_alter_table("system_settings") as batch:
        batch.add_column(
            sa.Column(
                "mcp_beta_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("mcp_beta_enabled")
