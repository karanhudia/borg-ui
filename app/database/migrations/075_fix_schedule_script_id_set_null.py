"""Add ON DELETE SET NULL to scheduled_jobs.pre_backup_script_id and post_backup_script_id

The scheduled_jobs.pre_backup_script_id and post_backup_script_id foreign keys were
added in migration 037 without an ON DELETE action. When a script referenced by a
schedule is deleted, SQLite raises an IntegrityError because it cannot cascade or
nullify the child rows automatically.

This migration recreates the scheduled_jobs table with ON DELETE SET NULL on both
script FK columns, so that deleting a script automatically clears the reference in
any schedule that used it.

The migration is fully idempotent:
- Skips immediately if ON DELETE SET NULL is already present (subsequent startups).
- Builds the new table DDL from PRAGMA table_info so it is immune to columns
  added by later migrations.
- Uses the table-recreation pattern required by SQLite (ALTER TABLE cannot
  modify FK constraints).
"""

from sqlalchemy import text


def upgrade(connection):
    """Add ON DELETE SET NULL to scheduled_jobs script FK columns"""

    # ── Idempotency guard ────────────────────────────────────────────────────
    # PRAGMA foreign_key_list returns rows:
    #   (id, seq, table, from, to, on_update, on_delete, match)
    # row[3] is the "from" column; row[6] is the on_delete action
    fk_rows = connection.execute(
        text("PRAGMA foreign_key_list(scheduled_jobs)")
    ).fetchall()

    script_fk_cols = {row[3]: row[6] for row in fk_rows if row[2] == "scripts"}
    already_set_null = (
        script_fk_cols.get("pre_backup_script_id") == "SET NULL" and
        script_fk_cols.get("post_backup_script_id") == "SET NULL"
    )

    if already_set_null:
        print("✓ scheduled_jobs script FKs already have ON DELETE SET NULL — skipping migration 075")
        return

    print("⚠️  Fixing scheduled_jobs script FK constraints (adding ON DELETE SET NULL)...")

    try:
        # ── Build new table DDL from the live schema ─────────────────────────
        # PRAGMA table_info rows: (cid, name, type, notnull, dflt_value, pk)
        col_rows = connection.execute(
            text("PRAGMA table_info(scheduled_jobs)")
        ).fetchall()

        col_defs = []
        for _cid, name, type_, notnull, dflt_value, pk in col_rows:
            if pk:
                col_defs.append(f"    {name} {type_} PRIMARY KEY AUTOINCREMENT")
            else:
                parts = [f"    {name}", type_]
                if notnull:
                    parts.append("NOT NULL")
                if dflt_value is not None:
                    parts.append(f"DEFAULT {dflt_value}")
                col_defs.append(" ".join(parts))

        # Append all FK constraints; script FKs get ON DELETE SET NULL
        col_defs.append("    FOREIGN KEY (repository_id) REFERENCES repositories (id)")
        col_defs.append("    FOREIGN KEY (source_ssh_connection_id) REFERENCES ssh_connections (id)")
        col_defs.append(
            "    FOREIGN KEY (pre_backup_script_id) REFERENCES scripts (id) ON DELETE SET NULL"
        )
        col_defs.append(
            "    FOREIGN KEY (post_backup_script_id) REFERENCES scripts (id) ON DELETE SET NULL"
        )

        new_ddl = "CREATE TABLE scheduled_jobs_new (\n" + ",\n".join(col_defs) + "\n)"

        # ── Disable FK enforcement for the drop/rename swap ──────────────────
        # Required because backup_jobs and scheduled_job_repositories reference
        # scheduled_jobs; SQLite blocks DROP TABLE when child rows exist.
        connection.execute(text("PRAGMA foreign_keys = OFF"))

        try:
            # ── Guard against stale temp table from a previous interrupted run ─
            connection.execute(text("DROP TABLE IF EXISTS scheduled_jobs_new"))
            connection.execute(text(new_ddl))

            # ── Copy using explicit column names ──────────────────────────────
            col_names = ", ".join(row[1] for row in col_rows)
            connection.execute(text(
                f"INSERT INTO scheduled_jobs_new ({col_names})"
                f" SELECT {col_names} FROM scheduled_jobs"
            ))

            # ── Swap tables ───────────────────────────────────────────────────
            connection.execute(text("DROP TABLE scheduled_jobs"))
            connection.execute(text("ALTER TABLE scheduled_jobs_new RENAME TO scheduled_jobs"))

            # ── Recreate indexes ──────────────────────────────────────────────
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_scheduled_jobs_name ON scheduled_jobs (name)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scheduled_jobs_id ON scheduled_jobs (id)"
            ))
        finally:
            connection.execute(text("PRAGMA foreign_keys = ON"))

        print("✓ scheduled_jobs.pre_backup_script_id FK now has ON DELETE SET NULL")
        print("✓ scheduled_jobs.post_backup_script_id FK now has ON DELETE SET NULL")
        print("✓ Scripts can now be deleted even when referenced by schedules")

    except Exception as e:
        print(f"✗ Error fixing scheduled_jobs script FK constraints: {e}")
        print("  Note: Deleting scripts referenced by schedules may still fail at DB level")
        # Don't raise - allow migration to continue


def downgrade(connection):
    """No downgrade action - removing SET NULL would re-introduce the IntegrityError bug"""
    print("✓ Downgrade skipped — reverting ON DELETE SET NULL would restore the IntegrityError bug")
