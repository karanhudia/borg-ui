"""add archives.stats_measured_at

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ALTER like f2a3b4c5d6e7: a batch rebuild of `archives` on SQLite
    # would cascade-delete every archive_changes row.
    op.add_column(
        "archives", sa.Column("stats_measured_at", sa.DateTime(), nullable=True)
    )
    # A row with sizes was measured in the listing run that created it
    # (spec 4.1); first_seen_at is the honest date. Rows without sizes stay
    # NULL and the info loop picks them up as before.
    op.execute(
        "UPDATE archives SET stats_measured_at = first_seen_at "
        "WHERE original_size IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("archives", "stats_measured_at")
