"""add MCP connections, settings and activity

Revision ID: e4b7c2a9d1f3
Revises: d3e8a1c6b2f9
Create Date: 2026-11-14

An MCP connection is an `api_tokens` row with kind "mcp" and an access
level. Existing rows become kind "api" and keep their full power. The admin
switch and level cap live on `system_settings`. `mcp_activity` keeps one row
per tool call (spec 2026-11-14-mcp-server, 5.2 and 5.11).
"""

import sqlalchemy as sa
from alembic import op

revision = "e4b7c2a9d1f3"
down_revision = "d3e8a1c6b2f9"
branch_labels = None
depends_on = None


def _add_missing(table: str, columns: list[sa.Column]) -> None:
    # Re-runnable: SQLite DDL is not transactional under Alembic.
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    missing = [column for column in columns if column.name not in existing]
    if missing:
        with op.batch_alter_table(table) as batch:
            for column in missing:
                batch.add_column(column)


def upgrade() -> None:
    _add_missing(
        "api_tokens",
        [
            sa.Column("kind", sa.String(8), nullable=False, server_default="api"),
            sa.Column("access_level", sa.String(16), nullable=True),
            sa.Column(
                "skip_routine_confirmations",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("last_client_name", sa.String(100), nullable=True),
            sa.Column("last_client_version", sa.String(100), nullable=True),
        ],
    )
    _add_missing(
        "system_settings",
        [
            sa.Column(
                "mcp_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "mcp_max_access_level",
                sa.String(16),
                nullable=False,
                server_default="full",
            ),
        ],
    )
    if "mcp_activity" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "mcp_activity",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "connection_id",
                sa.Integer(),
                sa.ForeignKey("api_tokens.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("connection_name", sa.String(), nullable=False),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("tool", sa.String(64), nullable=False),
            sa.Column("effective_level", sa.String(16), nullable=False),
            sa.Column("outcome", sa.String(32), nullable=False),
            sa.Column("error_key", sa.String(200), nullable=True),
            sa.Column("target", sa.String(200), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mcp_activity_id", "mcp_activity", ["id"])
        op.create_index("ix_mcp_activity_created_at", "mcp_activity", ["created_at"])
        op.create_index(
            "ix_mcp_activity_connection_created",
            "mcp_activity",
            ["connection_id", "created_at"],
        )


def downgrade() -> None:
    # Without the kind column an MCP token would read as a full-power
    # personal token after a later upgrade, so revoke them first.
    op.execute("DELETE FROM api_tokens WHERE kind = 'mcp'")
    op.drop_table("mcp_activity")
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("mcp_max_access_level")
        batch.drop_column("mcp_enabled")
    with op.batch_alter_table("api_tokens") as batch:
        batch.drop_column("last_client_version")
        batch.drop_column("last_client_name")
        batch.drop_column("skip_routine_confirmations")
        batch.drop_column("access_level")
        batch.drop_column("kind")
