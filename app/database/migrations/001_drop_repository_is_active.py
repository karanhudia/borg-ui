"""
Migration: Drop is_active column from repositories table

Run this once to remove the is_active column from existing databases.
This column was not being used functionally and only caused UI clutter.

Usage:
    python -m app.database.migrations.001_drop_repository_is_active
"""

import sqlite3
import os
import sys

def migrate():
    """Drop is_active column from repositories table"""

    # Database path
    db_path = os.environ.get("DATABASE_URL", "sqlite:///./data/borg_ui.db").replace("sqlite:///", "")

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        print("No migration needed - database will be created fresh without is_active column")
        return

    print(f"Migrating database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if is_active column exists
        cursor.execute("PRAGMA table_info(repositories)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'is_active' not in columns:
            print("✓ is_active column does not exist - no migration needed")
            conn.close()
            return

        print("Found is_active column - dropping it...")

        # SQLite doesn't support DROP COLUMN directly, so we need to:
        # 1. Create a new table without is_active
        # 2. Copy data from old table
        # 3. Drop old table
        # 4. Rename new table

        # Get current table structure
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='repositories'")
        create_statement = cursor.fetchone()[0]

        # Create new table without is_active
        cursor.execute("""
            CREATE TABLE repositories_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR UNIQUE NOT NULL,
                path VARCHAR UNIQUE NOT NULL,
                encryption VARCHAR DEFAULT 'repokey',
                compression VARCHAR DEFAULT 'lz4',
                passphrase VARCHAR,
                source_directories TEXT,
                last_backup DATETIME,
                total_size VARCHAR,
                archive_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                repository_type VARCHAR DEFAULT 'local',
                host VARCHAR,
                port INTEGER DEFAULT 22,
                username VARCHAR,
                ssh_key_id INTEGER,
                auth_status VARCHAR DEFAULT 'unknown',
                last_auth_test DATETIME,
                auth_error_message TEXT,
                FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys (id)
            )
        """)

        # Copy data (excluding is_active column)
        cursor.execute("""
            INSERT INTO repositories_new
            SELECT id, name, path, encryption, compression, passphrase, source_directories,
                   last_backup, total_size, archive_count, created_at, updated_at,
                   repository_type, host, port, username, ssh_key_id,
                   auth_status, last_auth_test, auth_error_message
            FROM repositories
        """)

        # Drop old table
        cursor.execute("DROP TABLE repositories")

        # Rename new table
        cursor.execute("ALTER TABLE repositories_new RENAME TO repositories")

        # Recreate indexes
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_repositories_name ON repositories (name)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_repositories_path ON repositories (path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_repositories_id ON repositories (id)")

        conn.commit()
        print("✓ Successfully dropped is_active column from repositories table")

    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
