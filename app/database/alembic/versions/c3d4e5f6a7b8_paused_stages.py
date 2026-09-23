"""pause background work per stage

The global background_paused flag becomes the list of paused stages, so the
Background work board can pause one stage at a time. A paused install comes
out with every stage paused.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-23
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

# Frozen copy of vocab.STAGES keys: a migration must not follow later edits.
ALL_STAGES = ["archives", "retention", "history", "stats"]


def upgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column("paused_stages", sa.JSON(), nullable=False, server_default="[]")
        )
    op.execute(
        sa.text(
            "UPDATE system_settings SET paused_stages = :stages WHERE background_paused"
        ).bindparams(stages=json.dumps(ALL_STAGES))
    )
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("background_paused")


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "background_paused",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, paused_stages FROM system_settings"))
    for row_id, stages in rows.fetchall():
        paused = set(json.loads(stages or "[]")) >= set(ALL_STAGES)
        bind.execute(
            sa.text("UPDATE system_settings SET background_paused = :p WHERE id = :id"),
            {"p": paused, "id": row_id},
        )
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("paused_stages")
