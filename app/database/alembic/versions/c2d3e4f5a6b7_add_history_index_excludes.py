"""add repository history index excludes and history bootstrap flag

Revision ID: c2d3e4f5a6b7
Revises: b1e2f3a4c5d6
Create Date: 2026-09-04
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1e2f3a4c5d6"
branch_labels = None
depends_on = None

# Mirrors app.database.models.DEFAULT_HISTORY_INDEX_EXCLUDES. Copied so the
# migration does not import application code.
DEFAULT_EXCLUDES = [
    "**/.cache/**",
    "**/Library/Caches/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.git/objects/**",
]


def upgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(sa.Column("history_index_excludes", sa.JSON(), nullable=True))
    with op.batch_alter_table("system_settings") as batch:
        batch.add_column(
            sa.Column("history_bootstrap_at", sa.DateTime(), nullable=True)
        )
    op.execute(
        sa.text(
            "UPDATE repositories SET history_index_excludes = :value "
            "WHERE history_index_excludes IS NULL"
        ).bindparams(value=json.dumps(DEFAULT_EXCLUDES))
    )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("history_bootstrap_at")
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("history_index_excludes")
