"""Support agent-published pre/post scripts in backup-plan hooks.

Adds ``agent_script_name`` to ``backup_plan_scripts`` and ``script_executions``
and relaxes their ``script_id`` NOT NULL constraint, so a hook (and its execution
history) can reference EITHER a server-side library script (``script_id``) OR a
named script the agent publishes (``agent_script_name``).

Purely additive: existing rows keep their ``script_id``; ``agent_script_name`` is
NULL for every current hook. SQLite cannot ALTER a column's nullability in place,
so ``script_id`` is relaxed with the established table-recreation pattern
(see migration 067). The rebuild is PRAGMA-driven so it preserves columns added
by later migrations, foreign keys (with their ON DELETE actions) and indexes.

Idempotent: adding the column is guarded on its presence, and the rebuild is
skipped once ``script_id`` is already nullable.
"""

from sqlalchemy import text


def _columns(connection, table):
    return connection.execute(text(f"PRAGMA table_info({table})")).fetchall()


def _has_table(connection, table):
    return bool(_columns(connection, table))


def _add_column_if_missing(connection, table, column, ddl_type):
    names = {row[1] for row in _columns(connection, table)}
    if column not in names:
        connection.execute(
            text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
        )


def _script_id_is_notnull(connection, table):
    # PRAGMA table_info rows: (cid, name, type, notnull, dflt_value, pk)
    for _cid, name, _type, notnull, _dflt, _pk in _columns(connection, table):
        if name == "script_id":
            return bool(notnull)
    return False


def _relax_script_id_notnull(connection, table, *, extra_unique=None):
    """Recreate ``table`` with ``script_id`` nullable, preserving everything else."""
    if not _has_table(connection, table) or not _script_id_is_notnull(
        connection, table
    ):
        return

    col_rows = _columns(connection, table)

    col_defs = []
    for _cid, name, type_, notnull, dflt_value, pk in col_rows:
        if pk:
            col_defs.append(f"    {name} {type_} PRIMARY KEY AUTOINCREMENT")
            continue
        parts = [f"    {name}", type_ or ""]
        if notnull and name != "script_id":  # relax script_id only
            parts.append("NOT NULL")
        if dflt_value is not None:
            parts.append(f"DEFAULT {dflt_value}")
        col_defs.append(" ".join(part for part in parts if part))

    # Foreign keys, preserving their ON DELETE / ON UPDATE actions.
    # PRAGMA foreign_key_list rows:
    #   (id, seq, table, from, to, on_update, on_delete, match)
    fk_rows = connection.execute(
        text(f"PRAGMA foreign_key_list({table})")
    ).fetchall()
    by_id = {}
    for row in fk_rows:
        by_id.setdefault(row[0], []).append(row)
    for _fid, rows in sorted(by_id.items()):
        rows = sorted(rows, key=lambda r: r[1])
        ref_table = rows[0][2]
        from_cols = ", ".join(r[3] for r in rows)
        to_cols = ", ".join(r[4] for r in rows)
        clause = f"    FOREIGN KEY ({from_cols}) REFERENCES {ref_table} ({to_cols})"
        on_delete = rows[0][6]
        on_update = rows[0][5]
        if on_delete and on_delete.upper() != "NO ACTION":
            clause += f" ON DELETE {on_delete}"
        if on_update and on_update.upper() != "NO ACTION":
            clause += f" ON UPDATE {on_update}"
        col_defs.append(clause)

    # Named indexes (auto-indexes for UNIQUE constraints have sql=NULL and are
    # handled separately via ``extra_unique``).
    index_sqls = [
        row[0]
        for row in connection.execute(
            text(
                "SELECT sql FROM sqlite_master"
                " WHERE type = 'index' AND tbl_name = :table AND sql IS NOT NULL"
            ),
            {"table": table},
        ).fetchall()
    ]

    col_names = ", ".join(row[1] for row in col_rows)
    new_ddl = f"CREATE TABLE {table}_new (\n" + ",\n".join(col_defs) + "\n)"

    connection.execute(text(f"DROP TABLE IF EXISTS {table}_new"))
    connection.execute(text(new_ddl))
    connection.execute(
        text(
            f"INSERT INTO {table}_new ({col_names})"
            f" SELECT {col_names} FROM {table}"
        )
    )
    connection.execute(text(f"DROP TABLE {table}"))
    connection.execute(text(f"ALTER TABLE {table}_new RENAME TO {table}"))

    for sql in index_sqls:
        connection.execute(text(sql))
    if extra_unique:
        name, columns = extra_unique
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {name}"
                f" ON {table} ({', '.join(columns)})"
            )
        )


def upgrade(connection):
    if _has_table(connection, "backup_plan_scripts"):
        _add_column_if_missing(
            connection, "backup_plan_scripts", "agent_script_name", "VARCHAR(255)"
        )
        _relax_script_id_notnull(
            connection,
            "backup_plan_scripts",
            extra_unique=(
                "uq_backup_plan_script",
                ["backup_plan_id", "script_id", "hook_type"],
            ),
        )

    if _has_table(connection, "script_executions"):
        _add_column_if_missing(
            connection, "script_executions", "agent_script_name", "VARCHAR(255)"
        )
        _relax_script_id_notnull(connection, "script_executions")


def downgrade(connection):
    # No downgrade: re-imposing NOT NULL would break any agent-script rows and
    # dropping the column is unnecessary (it is nullable and additive).
    print("✓ Downgrade skipped for migration 126 (additive, non-destructive)")
