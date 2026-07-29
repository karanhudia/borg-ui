"""Fix package_install_jobs package_id FK to add ON DELETE CASCADE

The package_install_jobs.package_id foreign key was originally created without
ON DELETE CASCADE. This causes an IntegrityError when attempting to delete an
installed_packages row that still has rows in package_install_jobs.

This migration recreates the package_install_jobs table with the corrected FK
declaration (ON DELETE CASCADE) so that deleting an installed package
automatically removes all associated install job records.

The migration is fully idempotent:
- Skips immediately if ON DELETE CASCADE is already present (subsequent startups).
- Builds the new table DDL from PRAGMA table_info so it is immune to columns
  added by later migrations.
- Uses the table-recreation pattern required by SQLite (ALTER TABLE cannot
  modify FK constraints).
"""

from sqlalchemy import text


def upgrade(connection):
    """Add ON DELETE CASCADE to package_install_jobs.package_id foreign key"""

    # ── Idempotency guard ────────────────────────────────────────────────────
    # PRAGMA foreign_key_list returns rows:
    #   (id, seq, table, from, to, on_update, on_delete, match)
    # row[4] == "id" identifies the FK pointing to installed_packages.id
    # row[6] == "CASCADE" confirms ON DELETE CASCADE is already present
    fk_rows = connection.execute(
        text("PRAGMA foreign_key_list(package_install_jobs)")
    ).fetchall()

    already_cascades = any(row[4] == "id" and row[6] == "CASCADE" for row in fk_rows)

    if already_cascades:
        print(
            "✓ package_install_jobs FK already has ON DELETE CASCADE — skipping migration 076"
        )
        return

    print(
        "⚠️  Fixing package_install_jobs package_id FK constraint (adding ON DELETE CASCADE)..."
    )

    try:
        # ── Build new table DDL from the live schema ─────────────────────────
        # PRAGMA table_info rows: (cid, name, type, notnull, dflt_value, pk)
        col_rows = connection.execute(
            text("PRAGMA table_info(package_install_jobs)")
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
            "    FOREIGN KEY (package_id) REFERENCES installed_packages(id) ON DELETE CASCADE"
        )

        new_ddl = (
            "CREATE TABLE package_install_jobs_new (\n" + ",\n".join(col_defs) + "\n)"
        )

        # ── Clean up orphaned rows before copying ────────────────────────────
        # FK enforcement is ON (set by SQLAlchemy event listener in database.py).
        # Rows whose package_id no longer exists in installed_packages would cause
        # the INSERT into the new table to fail. Delete them first.
        orphans = connection.execute(
            text(
                "SELECT COUNT(*) FROM package_install_jobs"
                " WHERE package_id NOT IN (SELECT id FROM installed_packages)"
            )
        ).scalar()
        if orphans:
            connection.execute(
                text(
                    "DELETE FROM package_install_jobs"
                    " WHERE package_id NOT IN (SELECT id FROM installed_packages)"
                )
            )
            print(
                f"  Removed {orphans} orphaned package_install_jobs row(s) with no matching package"
            )

        # ── Guard against stale temp table from a previous interrupted run ───
        connection.execute(text("DROP TABLE IF EXISTS package_install_jobs_new"))
        connection.execute(text(new_ddl))

        # ── Copy using explicit column names (avoids SELECT * count mismatch) ─
        col_names = ", ".join(row[1] for row in col_rows)
        connection.execute(
            text(
                f"INSERT INTO package_install_jobs_new ({col_names})"
                f" SELECT {col_names} FROM package_install_jobs"
            )
        )

        # ── Swap tables ───────────────────────────────────────────────────────
        connection.execute(text("DROP TABLE package_install_jobs"))
        connection.execute(
            text("ALTER TABLE package_install_jobs_new RENAME TO package_install_jobs")
        )

        print(
            "✓ package_install_jobs foreign key constraint fixed (ON DELETE CASCADE added)"
        )
        print(
            "✓ Installed packages can now be deleted even when install job records exist"
        )

    except Exception as e:
        print(f"✗ Error fixing package_install_jobs FK constraint: {e}")
        print("  Note: Deleting packages with install jobs may still fail at DB level")
        # Don't raise - allow migration to continue


def downgrade(connection):
    """No downgrade action - removing CASCADE would re-introduce the IntegrityError bug"""
    print(
        "✓ Downgrade skipped — reverting ON DELETE CASCADE would restore the IntegrityError bug"
    )
