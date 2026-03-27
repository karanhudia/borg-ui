"""Fix remaining FK actions on script_executions table

Migration 067 added ON DELETE CASCADE for backup_job_id, but left three other
foreign keys without proper ON DELETE actions:

  - script_id REFERENCES scripts(id)           → no action
  - repository_id REFERENCES repositories(id)  → no action
  - triggered_by_user_id REFERENCES users(id)  → no action

This causes IntegrityError when:
  1. A repository is deleted that has associated script execution history
     (delete_repository does NOT clean up script_executions)
  2. A user is deleted who triggered script executions

Fix:
  - script_id: ON DELETE CASCADE (script deleted → executions deleted)
  - repository_id: ON DELETE SET NULL (repo deleted → execution.repository_id = NULL)
  - triggered_by_user_id: ON DELETE SET NULL (user deleted → execution.triggered_by_user_id = NULL)
  - backup_job_id: ON DELETE CASCADE (preserved from migration 067)

The migration is fully idempotent:
- Skips if repository_id FK already has ON DELETE SET NULL.
- Uses table-recreation pattern (SQLite cannot ALTER FK constraints).
- Cleans orphaned rows before copying to avoid INSERT failures.
"""

from sqlalchemy import text


def upgrade(connection):
    """Fix ON DELETE actions for script_executions foreign keys"""

    # ── Idempotency guard ─────────────────────────────────────────────────────
    # Check if repository_id already has SET NULL (implies this migration ran)
    fk_rows = connection.execute(
        text("PRAGMA foreign_key_list(script_executions)")
    ).fetchall()

    already_fixed = any(row[3] == "repository_id" and row[6] == "SET NULL" for row in fk_rows)

    if already_fixed:
        print("✓ script_executions FK actions already fixed — skipping migration 077")
        return

    print("⚠️  Fixing script_executions FK actions (script_id CASCADE, repository_id/triggered_by_user_id SET NULL)...")

    try:
        # ── Build new table DDL from the live schema ──────────────────────────
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

        # Append all FK constraints with correct ON DELETE actions
        col_defs.append(
            "    FOREIGN KEY (script_id) REFERENCES scripts (id) ON DELETE CASCADE"
        )
        col_defs.append(
            "    FOREIGN KEY (repository_id) REFERENCES repositories (id) ON DELETE SET NULL"
        )
        col_defs.append(
            "    FOREIGN KEY (backup_job_id) REFERENCES backup_jobs (id) ON DELETE CASCADE"
        )
        col_defs.append(
            "    FOREIGN KEY (triggered_by_user_id) REFERENCES users (id) ON DELETE SET NULL"
        )

        new_ddl = "CREATE TABLE script_executions_new (\n" + ",\n".join(col_defs) + "\n)"

        # ── Clean up orphaned rows to prevent INSERT failures ─────────────────
        # FK enforcement is ON; rows referencing deleted parents cause INSERT errors.
        # NULL out orphaned repository_id references
        orphan_repos = connection.execute(text(
            "SELECT COUNT(*) FROM script_executions"
            " WHERE repository_id IS NOT NULL"
            " AND repository_id NOT IN (SELECT id FROM repositories)"
        )).scalar()
        if orphan_repos:
            connection.execute(text(
                "UPDATE script_executions SET repository_id = NULL"
                " WHERE repository_id IS NOT NULL"
                " AND repository_id NOT IN (SELECT id FROM repositories)"
            ))
            print(f"  Nulled {orphan_repos} orphaned repository_id reference(s) in script_executions")

        # NULL out orphaned triggered_by_user_id references
        orphan_users = connection.execute(text(
            "SELECT COUNT(*) FROM script_executions"
            " WHERE triggered_by_user_id IS NOT NULL"
            " AND triggered_by_user_id NOT IN (SELECT id FROM users)"
        )).scalar()
        if orphan_users:
            connection.execute(text(
                "UPDATE script_executions SET triggered_by_user_id = NULL"
                " WHERE triggered_by_user_id IS NOT NULL"
                " AND triggered_by_user_id NOT IN (SELECT id FROM users)"
            ))
            print(f"  Nulled {orphan_users} orphaned triggered_by_user_id reference(s) in script_executions")

        # Delete rows with orphaned script_id (script was deleted, row should go too)
        orphan_scripts = connection.execute(text(
            "SELECT COUNT(*) FROM script_executions"
            " WHERE script_id NOT IN (SELECT id FROM scripts)"
        )).scalar()
        if orphan_scripts:
            connection.execute(text(
                "DELETE FROM script_executions"
                " WHERE script_id NOT IN (SELECT id FROM scripts)"
            ))
            print(f"  Deleted {orphan_scripts} orphaned script_executions row(s) with no matching script")

        # ── Guard against stale temp table ────────────────────────────────────
        connection.execute(text("DROP TABLE IF EXISTS script_executions_new"))
        connection.execute(text(new_ddl))

        # ── Copy using explicit column names ──────────────────────────────────
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

        print("✓ script_executions FK actions fixed")
        print("  - script_id: ON DELETE CASCADE")
        print("  - repository_id: ON DELETE SET NULL")
        print("  - backup_job_id: ON DELETE CASCADE (preserved)")
        print("  - triggered_by_user_id: ON DELETE SET NULL")
        print("✓ Repositories and users can now be deleted without IntegrityError from script_executions")

    except Exception as e:
        print(f"✗ Error fixing script_executions FK actions: {e}")
        print("  Note: Deleting repositories/users with script execution history may still fail")
        # Don't raise - allow migration to continue


def downgrade(connection):
    """No downgrade action - reverting would restore IntegrityError bugs"""
    print("✓ Downgrade skipped — reverting FK actions would restore IntegrityError bugs")
