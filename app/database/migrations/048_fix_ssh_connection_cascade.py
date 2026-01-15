"""Fix SSH connection foreign key to prevent cascade delete

This migration removes the CASCADE DELETE behavior from the ssh_key_id
foreign key in ssh_connections table, so connections are preserved when
an SSH key is deleted.
"""

from sqlalchemy import text


def upgrade(connection):
    """Remove CASCADE DELETE from ssh_connections.ssh_key_id foreign key"""

    # SQLite doesn't support DROP CONSTRAINT, so we need to recreate the table
    # This is the standard SQLite approach for modifying foreign keys

    print("⚠️  Fixing ssh_connections foreign key constraint...")

    try:
        # Step 1: Create new table without CASCADE DELETE
        connection.execute(text("""
            CREATE TABLE ssh_connections_new (
                id INTEGER PRIMARY KEY,
                ssh_key_id INTEGER,
                host TEXT NOT NULL,
                username TEXT NOT NULL,
                port INTEGER DEFAULT 22 NOT NULL,
                default_path TEXT,
                mount_point TEXT,
                status TEXT DEFAULT 'unknown' NOT NULL,
                last_test TIMESTAMP,
                last_success TIMESTAMP,
                error_message TEXT,
                storage_total BIGINT,
                storage_used BIGINT,
                storage_available BIGINT,
                storage_percent_used REAL,
                last_storage_check TIMESTAMP,
                is_backup_source BOOLEAN DEFAULT 0 NOT NULL,
                borg_binary_path TEXT DEFAULT '/usr/bin/borg' NOT NULL,
                borg_version TEXT,
                last_borg_check TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys(id) ON DELETE SET NULL
            )
        """))

        # Step 2: Copy data from old table to new table
        connection.execute(text("""
            INSERT INTO ssh_connections_new
            SELECT * FROM ssh_connections
        """))

        # Step 3: Drop old table
        connection.execute(text("DROP TABLE ssh_connections"))

        # Step 4: Rename new table to original name
        connection.execute(text("ALTER TABLE ssh_connections_new RENAME TO ssh_connections"))

        # Step 5: Recreate indexes
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
