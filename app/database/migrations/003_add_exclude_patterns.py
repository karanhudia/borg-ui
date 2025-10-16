"""
Migration: Add exclude_patterns column to repositories table

Run this once to add the exclude_patterns column for specifying backup exclusion patterns.

Usage:
    python -m app.database.migrations.003_add_exclude_patterns
"""

import sqlite3
import os
import sys

def migrate():
    """Add exclude_patterns column to repositories table"""

    # Database path
    db_path = os.environ.get("DATABASE_URL", "sqlite:///./data/borg_ui.db").replace("sqlite:///", "")

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        print("No migration needed - database will be created fresh with exclude_patterns column")
        return

    print(f"Migrating database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if exclude_patterns column exists
        cursor.execute("PRAGMA table_info(repositories)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'exclude_patterns' in columns:
            print("✓ exclude_patterns column already exists - no migration needed")
            conn.close()
            return

        print("Adding exclude_patterns column...")

        # Add the column (SQLite supports ALTER TABLE ADD COLUMN)
        cursor.execute("""
            ALTER TABLE repositories
            ADD COLUMN exclude_patterns TEXT
        """)

        conn.commit()
        print("✓ Successfully added exclude_patterns column to repositories table")

    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
