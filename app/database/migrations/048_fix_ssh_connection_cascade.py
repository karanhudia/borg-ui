"""Fix SSH connection foreign key to prevent cascade delete

This migration removes the CASCADE DELETE behavior from the ssh_key_id
foreign key in ssh_connections table, so connections are preserved when
an SSH key is deleted.

The migration is fully idempotent:
- Skips immediately if the CASCADE is already gone (subsequent startups).
- Builds the new table DDL from PRAGMA table_info so it is immune to
  columns added by later migrations (e.g. use_sftp_mode, ssh_path_prefix).
"""

from sqlalchemy import text


def upgrade(connection):
    """Remove CASCADE DELETE from ssh_connections.ssh_key_id foreign key"""

    # ── Idempotency guard ────────────────────────────────────────────────────
    # PRAGMA foreign_key_list returns rows:
    #   (id, seq, table, from, to, on_update, on_delete, match)
    fk_rows = connection.execute(
        text("PRAGMA foreign_key_list(ssh_connections)")
    ).fetchall()

    has_cascade = any(row[6] == "CASCADE" for row in fk_rows)

    if not has_cascade:
        print("✓ ssh_connections FK already uses SET NULL — skipping migration 048")
        return

    print("⚠️  Fixing ssh_connections foreign key constraint...")

    try:
        # ── Build new table DDL from the live schema ─────────────────────────
        # PRAGMA table_info rows: (cid, name, type, notnull, dflt_value, pk)
        col_rows = connection.execute(
            text("PRAGMA table_info(ssh_connections)")
        ).fetchall()

        col_defs = []
        for _cid, name, type_, notnull, dflt_value, pk in col_rows:
            if pk:
                col_defs.append(f"    {name} {type_} PRIMARY KEY")
            else:
                parts = [f"    {name}", type_]
                if notnull:
                    parts.append("NOT NULL")
                if dflt_value is not None:
                    parts.append(f"DEFAULT {dflt_value}")
                col_defs.append(" ".join(parts))

        # Append the corrected FK (SET NULL instead of CASCADE)
        col_defs.append(
            "    FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys(id) ON DELETE SET NULL"
        )

        new_ddl = "CREATE TABLE ssh_connections_new (\n" + ",\n".join(col_defs) + "\n)"

        # ── Guard against stale temp table from a previous interrupted run ───
        connection.execute(text("DROP TABLE IF EXISTS ssh_connections_new"))
        connection.execute(text(new_ddl))

        # ── Copy using explicit column names (avoids SELECT * count mismatch) ─
        col_names = ", ".join(row[1] for row in col_rows)
        connection.execute(text(
            f"INSERT INTO ssh_connections_new ({col_names})"
            f" SELECT {col_names} FROM ssh_connections"
        ))

        # ── Swap tables ───────────────────────────────────────────────────────
        connection.execute(text("DROP TABLE ssh_connections"))
        connection.execute(text("ALTER TABLE ssh_connections_new RENAME TO ssh_connections"))

        # ── Recreate index ────────────────────────────────────────────────────
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ssh_connections_ssh_key_id
            ON ssh_connections(ssh_key_id)
        """))

        print("✓ SSH connection foreign key constraint fixed")
        print("✓ Connections will now be preserved when SSH keys are deleted")

    except Exception as e:
        print(f"✗ Error fixing foreign key constraint: {e}")
        print("  Note: If this fails, connections may still be deleted when keys are removed")
        # Don't raise - allow migration to continue


def downgrade(connection):
    """Restore CASCADE DELETE behavior (not recommended)"""
    print("✓ Downgrade skipped - keeping SET NULL behavior for safety")
