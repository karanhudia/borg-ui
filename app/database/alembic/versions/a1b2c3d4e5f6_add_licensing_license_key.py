"""store the license key on licensing_state

Seat management (list seats on this license, release a stale one) authenticates
to the license service with the license key, so the instance has to keep the key
it was activated with. Encrypted at rest by the EncryptedString column type.

Revision ID: a1b2c3d4e5f6
Revises: a7c3e9f1b5d2
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "a7c3e9f1b5d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic does not run SQLite DDL in a transaction: a boot killed after
    # the ALTER but before the version bump keeps the column, and re-running
    # this revision must not fail on the duplicate. Self-contained on purpose.
    existing = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("licensing_state")
    }
    missing = [
        column
        for column in (sa.Column("license_key_encrypted", sa.String(), nullable=True),)
        if column.name not in existing
    ]
    if missing:
        with op.batch_alter_table("licensing_state") as batch:
            for column in missing:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("licensing_state") as batch_op:
        batch_op.drop_column("license_key_encrypted")
