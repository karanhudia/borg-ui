"""Column additions that survive a re-run of their revision.

Alembic does not run SQLite DDL in a transaction: an upgrade killed between a
plain ALTER TABLE ADD COLUMN and the version bump keeps the column, and every
later boot re-runs the revision and fails on the duplicate. A rewound version
pointer has the same shape. Adding only the missing columns makes such a
revision safe to repeat.
"""

import sqlalchemy as sa
from alembic import op


def add_missing_columns(table: str, *columns: sa.Column) -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    missing = [c for c in columns if c.name not in existing]
    if not missing:
        return
    with op.batch_alter_table(table) as batch:
        for column in missing:
            batch.add_column(column)
