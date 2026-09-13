"""add repository size bytes and measured_at

Revision ID: a9b8c7d6e5f4
Revises: e1f2a3b4c5d6
Create Date: 2026-09-11
"""

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from alembic import op
import sqlalchemy as sa

revision = "a9b8c7d6e5f4"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

# The units a stored size string may carry: what `format_bytes` prints
# (base 1024, two decimals) and the shapes older releases wrote ("1.5GB",
# "1 GiB", a bare byte count). A copy of `storage_usage.bytes_from_formatted`
# (a migration imports no app code): keep the two in step.
_SIZE_UNITS = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}
_SIZE_TEXT = re.compile(
    r"^\s*(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>[KMGTPE]?)(?:I?B)?\s*$", re.IGNORECASE
)


def bytes_from_formatted(text: Optional[str]) -> Optional[int]:
    """The byte count a stored size string stands for, as exact as its
    digits allow; None for anything else ("Unknown", "N/A", empty)."""
    if not text:
        return None
    match = _SIZE_TEXT.match(text)
    if not match:
        return None
    # the pattern admits digits and one point only, so the value is finite
    value = Decimal(match.group("number"))
    exponent = _SIZE_UNITS[match.group("unit").upper()]
    scaled = value * (Decimal(1024) ** exponent)
    return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))


def upgrade() -> None:
    # The size as measured, next to the formatted string the card shows:
    # readers that need a number (the archive header, the info dialog, a
    # storage total) no longer parse the string back. `measured_at` is when
    # that value was written.
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(sa.Column("total_size_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column("total_size_measured_at", sa.DateTime(), nullable=True)
        )
    # Backfill from the string every row already carries, so a repository
    # that showed a size keeps showing one in the new field; the two
    # decimals of the string are all the precision there is until the next
    # measurement rewrites both. The time of that old measurement is not
    # known, so `measured_at` stays NULL until then: a size with no time is
    # the backfilled state, and the readers say so.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, total_size FROM repositories WHERE total_size IS NOT NULL")
    ).fetchall()
    updates = [
        {"size_bytes": size_bytes, "id": repository_id}
        for repository_id, total_size in rows
        if (size_bytes := bytes_from_formatted(total_size)) is not None
    ]
    if updates:
        # one statement, not one round trip per repository
        connection.execute(
            sa.text(
                "UPDATE repositories SET total_size_bytes = :size_bytes WHERE id = :id"
            ),
            updates,
        )


def downgrade() -> None:
    # On SQLite a dropped column means a table recreate (copy, DROP TABLE,
    # rename), and DROP TABLE with foreign keys enforced deletes through
    # every ON DELETE CASCADE that points at `repositories`: the archive
    # index and the operation history. The pragma cannot be changed inside
    # the migration's transaction (a silent no-op), so it is switched in an
    # autocommit block around the recreate.
    # The pragma is not switched back: entering a second autocommit block
    # after the recreate would commit the DDL before Alembic writes the
    # version row, and a stop in between would leave a database without
    # the columns that still claims this revision. The recreate and the
    # version row commit together; the connection ends with the pragma
    # off, which affects nothing beyond this run (the upgrade runner
    # disposes its engine, and the application sets the pragma on
    # connect).
    if op.get_bind().dialect.name == "sqlite":
        with op.get_context().autocommit_block():
            op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("total_size_measured_at")
        batch.drop_column("total_size_bytes")
