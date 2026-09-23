"""pause background work per stage

The global background_paused flag becomes the list of paused stages, so the
Background work board can pause one stage at a time. A paused install comes
out with every stage paused.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

# Frozen copy of vocab.STAGES keys: a migration must not follow later edits.
ALL_STAGES = ["archives", "retention", "history", "stats"]

# Typed columns, so the JSON value is bound and read as JSON on every
# dialect: PostgreSQL refuses a text parameter for a json column, and
# psycopg hands the value back already decoded.
_settings = sa.table(
    "system_settings",
    sa.column("id", sa.Integer),
    sa.column("background_paused", sa.Boolean),
    sa.column("paused_stages", sa.JSON),
)


def upgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column("paused_stages", sa.JSON(), nullable=False, server_default="[]")
        )
    op.execute(
        _settings.update()
        .where(_settings.c.background_paused.is_(True))
        .values(paused_stages=ALL_STAGES)
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
    rows = bind.execute(sa.select(_settings.c.id, _settings.c.paused_stages))
    for row_id, stages in rows.fetchall():
        bind.execute(
            _settings.update()
            .where(_settings.c.id == row_id)
            .values(background_paused=set(stages or []) >= set(ALL_STAGES))
        )
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("paused_stages")
