"""
Migration: Add remote_path column to repositories table

Run this once to add the remote_path column for specifying borg location on remote servers.

Usage:
    python -m app.database.migrations.002_add_repository_remote_path
"""

import sqlite3
import os
import sys

def migrate():
    """Add remote_path column to repositories table"""

    # Database path
    db_path = os.environ.get("DATABASE_URL", "sqlite:///./data/borg_ui.db").replace("sqlite:///", "")

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        print("No migration needed - database will be created fresh with remote_path column")
        return

    print(f"Migrating database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if remote_path column exists
        cursor.execute("PRAGMA table_info(repositories)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'remote_path' in columns:
            print("✓ remote_path column already exists - no migration needed")
            conn.close()
            return

        print("Adding remote_path column...")

        # Add the column (SQLite supports ALTER TABLE ADD COLUMN)
        cursor.execute("""
            ALTER TABLE repositories
            ADD COLUMN remote_path VARCHAR
        """)

        conn.commit()
        print("✓ Successfully added remote_path column to repositories table")

    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
