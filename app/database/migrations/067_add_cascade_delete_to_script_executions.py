"""Add CASCADE delete to script_executions.backup_job_id foreign key

When a backup job is deleted, automatically delete all related script executions.
This prevents foreign key constraint errors when deleting backup jobs from the activity feed.

Since SQLite doesn't support modifying foreign keys directly, we need to recreate
the table using the table-recreation pattern.

The migration is fully idempotent:
- Skips immediately if ON DELETE CASCADE is already present (subsequent startups).
- Builds the new table DDL from PRAGMA table_info so it is immune to columns
  added by later migrations.
- Uses DROP TABLE IF EXISTS to guard against stale temp tables from interrupted runs.
- Uses explicit column names in INSERT SELECT (avoids wildcard select) to avoid column mismatch.
"""

from sqlalchemy import text


def upgrade(connection):
    """Add ON DELETE CASCADE to script_executions.backup_job_id foreign key"""

    # ── Idempotency guard ────────────────────────────────────────────────────
    # PRAGMA foreign_key_list returns rows:
    #   (id, seq, table, from, to, on_update, on_delete, match)
    # row[3] is the "from" column; row[6] is the on_delete action
    fk_rows = connection.execute(
        text("PRAGMA foreign_key_list(script_executions)")
    ).fetchall()

    already_cascades = any(row[3] == "backup_job_id" and row[6] == "CASCADE" for row in fk_rows)

    if already_cascades:
        print("✓ script_executions.backup_job_id FK already has ON DELETE CASCADE — skipping migration 067")
        return

    print("⚠️  Fixing script_executions foreign key constraint (adding ON DELETE CASCADE to backup_job_id)...")

    try:
        # ── Build new table DDL from the live schema ─────────────────────────
        # PRAGMA table_info rows: (cid, name, type, notnull, dflt_value, pk)
        col_rows = connection.execute(
            text("PRAGMA table_info(script_executions)")
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

        # Append all four FK constraints; backup_job_id gets ON DELETE CASCADE
        col_defs.append("    FOREIGN KEY (script_id) REFERENCES scripts (id)")
        col_defs.append("    FOREIGN KEY (repository_id) REFERENCES repositories (id)")
        col_defs.append(
            "    FOREIGN KEY (backup_job_id) REFERENCES backup_jobs (id) ON DELETE CASCADE"
        )
        col_defs.append("    FOREIGN KEY (triggered_by_user_id) REFERENCES users (id)")

        new_ddl = "CREATE TABLE script_executions_new (\n" + ",\n".join(col_defs) + "\n)"

        # ── Guard against stale temp table from a previous interrupted run ───
        connection.execute(text("DROP TABLE IF EXISTS script_executions_new"))
        connection.execute(text(new_ddl))

        # ── Copy using explicit column names (avoids column count mismatch) ─────
        col_names = ", ".join(row[1] for row in col_rows)
        connection.execute(text(
            f"INSERT INTO script_executions_new ({col_names})"
            f" SELECT {col_names} FROM script_executions"
        ))

        # ── Swap tables ───────────────────────────────────────────────────────
        connection.execute(text("DROP TABLE script_executions"))
        connection.execute(text("ALTER TABLE script_executions_new RENAME TO script_executions"))

        # ── Recreate indexes ──────────────────────────────────────────────────
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_script_executions_script_id"
            " ON script_executions (script_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_script_executions_repository_id"
            " ON script_executions (repository_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_script_executions_backup_job_id"
            " ON script_executions (backup_job_id)"
        ))

        print("✓ script_executions.backup_job_id FK now has ON DELETE CASCADE")
        print("✓ Backup jobs can now be deleted without leaving orphaned script execution rows")

    except Exception as e:
        print(f"✗ Error fixing script_executions foreign key constraint: {e}")
        print("  Note: Deleting backup jobs with script executions may still fail")
        # Don't raise - allow migration to continue


def downgrade(connection):
    """No downgrade action - removing CASCADE would re-introduce the IntegrityError bug"""
    print("✓ Downgrade skipped — reverting ON DELETE CASCADE would restore the IntegrityError bug")
