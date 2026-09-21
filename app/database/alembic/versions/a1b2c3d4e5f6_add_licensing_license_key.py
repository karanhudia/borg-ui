"""store the license key on licensing_state

Seat management (list seats on this license, release a stale one) authenticates
to the license service with the license key, so the instance has to keep the key
it was activated with. Encrypted at rest by the EncryptedString column type.

Revision ID: a1b2c3d4e5f6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("licensing_state") as batch_op:
        batch_op.add_column(
            sa.Column("license_key_encrypted", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("licensing_state") as batch_op:
        batch_op.drop_column("license_key_encrypted")
