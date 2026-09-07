"""Track the agent version each endpoint should run, and in-flight upgrades.

Purely additive and idempotent: every column is nullable, NULL for every
existing row, and added only if missing. Mirrors migration 127.
"""

from sqlalchemy import text

_COLUMNS = (
    ("desired_agent_version", "VARCHAR"),
    ("desired_borg_version", "VARCHAR"),
    ("upgrade_state", "VARCHAR"),
    ("upgrade_requested_at", "DATETIME"),
    ("upgrade_target_version", "VARCHAR"),
    ("upgrade_error", "TEXT"),
)


def _columns(connection, table):
    return connection.execute(text(f"PRAGMA table_info({table})")).fetchall()


def _has_table(connection, table):
    return bool(_columns(connection, table))


def _add_column_if_missing(connection, table, column, ddl_type):
    names = {row[1] for row in _columns(connection, table)}
    if column not in names:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def upgrade(connection):
    if not _has_table(connection, "agent_machines"):
        return
    for column, ddl_type in _COLUMNS:
        _add_column_if_missing(connection, "agent_machines", column, ddl_type)


def downgrade(connection):
    # No downgrade: every column is nullable and additive.
    print("✓ Downgrade skipped for migration 129 (additive, non-destructive)")
