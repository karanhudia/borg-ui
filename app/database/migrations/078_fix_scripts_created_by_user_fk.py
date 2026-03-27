"""Fix scripts.created_by_user_id FK to add ON DELETE SET NULL

The scripts.created_by_user_id foreign key was created without an ON DELETE
action. This causes an IntegrityError when deleting a user who created scripts,
because SQLite blocks the parent-row delete.

Both delete_user endpoints (auth.py and settings.py) do a bare db.delete(user)
with no cleanup of scripts.created_by_user_id, so any user with scripts in the
library cannot be deleted.

Fix: ON DELETE SET NULL — user deleted → script.created_by_user_id = NULL
(the script record is preserved; only the user attribution is cleared)

The migration is fully idempotent:
- Skips if created_by_user_id FK already has ON DELETE SET NULL.
- Uses table-recreation pattern (SQLite cannot ALTER FK constraints).
- Cleans orphaned created_by_user_id references before copying.
"""

from sqlalchemy import text


def upgrade(connection):
    """Add ON DELETE SET NULL to scripts.created_by_user_id foreign key"""

    # ── Idempotency guard ─────────────────────────────────────────────────────
    fk_rows = connection.execute(
        text("PRAGMA foreign_key_list(scripts)")
    ).fetchall()

    already_fixed = any(row[3] == "created_by_user_id" and row[6] == "SET NULL" for row in fk_rows)

    if already_fixed:
        print("✓ scripts.created_by_user_id FK already has ON DELETE SET NULL — skipping migration 078")
        return

    print("⚠️  Fixing scripts.created_by_user_id FK constraint (adding ON DELETE SET NULL)...")

    try:
        # ── Build new table DDL from the live schema ──────────────────────────
        col_rows = connection.execute(
            text("PRAGMA table_info(scripts)")
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

        # Append the corrected FK (ON DELETE SET NULL)
        col_defs.append(
            "    FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE SET NULL"
        )

        new_ddl = "CREATE TABLE scripts_new (\n" + ",\n".join(col_defs) + "\n)"

        # ── Clean up orphaned created_by_user_id references ───────────────────
        orphan_users = connection.execute(text(
            "SELECT COUNT(*) FROM scripts"
            " WHERE created_by_user_id IS NOT NULL"
            " AND created_by_user_id NOT IN (SELECT id FROM users)"
        )).scalar()
        if orphan_users:
            connection.execute(text(
                "UPDATE scripts SET created_by_user_id = NULL"
                " WHERE created_by_user_id IS NOT NULL"
                " AND created_by_user_id NOT IN (SELECT id FROM users)"
            ))
            print(f"  Nulled {orphan_users} orphaned created_by_user_id reference(s) in scripts")

        # ── Guard against stale temp table ────────────────────────────────────
        connection.execute(text("DROP TABLE IF EXISTS scripts_new"))
        connection.execute(text(new_ddl))

        # ── Copy using explicit column names ──────────────────────────────────
        col_names = ", ".join(row[1] for row in col_rows)
        connection.execute(text(
            f"INSERT INTO scripts_new ({col_names})"
            f" SELECT {col_names} FROM scripts"
        ))

        # ── Swap tables ───────────────────────────────────────────────────────
        connection.execute(text("DROP TABLE scripts"))
        connection.execute(text("ALTER TABLE scripts_new RENAME TO scripts"))

        # ── Recreate indexes ──────────────────────────────────────────────────
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_scripts_name ON scripts (name)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scripts_id ON scripts (id)"
        ))

        print("✓ scripts.created_by_user_id FK now has ON DELETE SET NULL")
        print("✓ Users can now be deleted without IntegrityError from scripts table")

    except Exception as e:
        print(f"✗ Error fixing scripts.created_by_user_id FK constraint: {e}")
        print("  Note: Deleting users who created scripts may still fail at DB level")
        # Don't raise - allow migration to continue


def downgrade(connection):
    """No downgrade action - reverting would restore the IntegrityError bug"""
    print("✓ Downgrade skipped — reverting ON DELETE SET NULL would restore the IntegrityError bug")
