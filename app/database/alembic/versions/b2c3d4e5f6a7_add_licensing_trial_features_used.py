"""remember which feature trials this install has spent

The entitlement that granted a trial is cleared once it lapses, and with it
the only record that the trial ever ran. The offer then came back at every
lock, and the activation service refused it. This column outlives the
entitlement, so a spent trial stays spent and a later release's features are
the only ones still on offer.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("licensing_state") as batch_op:
        batch_op.add_column(sa.Column("trial_features_used", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("licensing_state") as batch_op:
        batch_op.drop_column("trial_features_used")
