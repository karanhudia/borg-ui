"""Fix delete_archive_jobs repository_id FK to add ON DELETE CASCADE

The delete_archive_jobs.repository_id foreign key was originally created in
migration 049 without ON DELETE CASCADE. This causes an IntegrityError when
attempting to delete a repository that still has rows in delete_archive_jobs,
because SQLite blocks the parent-row delete.

This migration recreates the delete_archive_jobs table with the corrected FK
declaration (ON DELETE CASCADE) so that deleting a repository automatically
removes all associated archive-deletion job records.

The migration is fully idempotent:
- Skips immediately if ON DELETE CASCADE is already present (subsequent startups).
- Builds the new table DDL from PRAGMA table_info so it is immune to columns
  added by later migrations.
- Uses the table-recreation pattern required by SQLite (ALTER TABLE cannot
  modify FK constraints).
"""

from sqlalchemy import text


def upgrade(connection):
    """Add ON DELETE CASCADE to delete_archive_jobs.repository_id foreign key"""

    # ── Idempotency guard ────────────────────────────────────────────────────
    # PRAGMA foreign_key_list returns rows:
    #   (id, seq, table, from, to, on_update, on_delete, match)
    # row[4] == "id" identifies the FK pointing to repositories.id
    # row[6] == "CASCADE" confirms ON DELETE CASCADE is already present
    fk_rows = connection.execute(
        text("PRAGMA foreign_key_list(delete_archive_jobs)")
    ).fetchall()

    already_cascades = any(row[4] == "id" and row[6] == "CASCADE" for row in fk_rows)

    if already_cascades:
        print("✓ delete_archive_jobs FK already has ON DELETE CASCADE — skipping migration 073")
        return

    print("⚠️  Fixing delete_archive_jobs foreign key constraint (adding ON DELETE CASCADE)...")

    try:
        # ── Build new table DDL from the live schema ─────────────────────────
        # PRAGMA table_info rows: (cid, name, type, notnull, dflt_value, pk)
        col_rows = connection.execute(
            text("PRAGMA table_info(delete_archive_jobs)")
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

        # Append the corrected FK (ON DELETE CASCADE)
        col_defs.append(
            "    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE"
        )

        new_ddl = "CREATE TABLE delete_archive_jobs_new (\n" + ",\n".join(col_defs) + "\n)"

        # ── Clean up orphaned rows before copying ────────────────────────────
        # FK enforcement is ON (set by SQLAlchemy event listener in database.py).
        # Rows whose repository_id no longer exists in repositories would cause
        # the INSERT into the new table to fail. Delete them first.
        orphans = connection.execute(text(
            "SELECT COUNT(*) FROM delete_archive_jobs"
            " WHERE repository_id NOT IN (SELECT id FROM repositories)"
        )).scalar()
        if orphans:
            connection.execute(text(
                "DELETE FROM delete_archive_jobs"
                " WHERE repository_id NOT IN (SELECT id FROM repositories)"
            ))
            print(f"  Removed {orphans} orphaned delete_archive_jobs row(s) with no matching repository")

        # ── Guard against stale temp table from a previous interrupted run ───
        connection.execute(text("DROP TABLE IF EXISTS delete_archive_jobs_new"))
        connection.execute(text(new_ddl))

        # ── Copy using explicit column names (avoids SELECT * count mismatch) ─
        col_names = ", ".join(row[1] for row in col_rows)
        connection.execute(text(
            f"INSERT INTO delete_archive_jobs_new ({col_names})"
            f" SELECT {col_names} FROM delete_archive_jobs"
        ))

        # ── Swap tables ───────────────────────────────────────────────────────
        connection.execute(text("DROP TABLE delete_archive_jobs"))
        connection.execute(text("ALTER TABLE delete_archive_jobs_new RENAME TO delete_archive_jobs"))

        print("✓ delete_archive_jobs foreign key constraint fixed (ON DELETE CASCADE added)")
        print("✓ Repositories can now be deleted even when delete_archive_jobs rows exist")

    except Exception as e:
        print(f"✗ Error fixing delete_archive_jobs foreign key constraint: {e}")
        print("  Note: Deleting repositories with archive deletion jobs may still fail")
        # Don't raise - allow migration to continue


def downgrade(connection):
    """No downgrade action - removing CASCADE would re-introduce the IntegrityError bug"""
    print("✓ Downgrade skipped — reverting ON DELETE CASCADE would restore the IntegrityError bug")
