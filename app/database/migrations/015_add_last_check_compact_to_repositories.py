"""
Migration 015: Add last_check and last_compact fields to repositories

This migration adds timestamp fields to track the last successful
check and compact operations for each repository.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add last_check and last_compact columns to repositories table"""

    # Check if last_check column exists
    try:
        connection.execute(text("""
            SELECT last_check FROM repositories LIMIT 1
        """))
        print("  Skipped (exists): last_check column")
    except Exception:
        connection.execute(text("""
            ALTER TABLE repositories ADD COLUMN last_check DATETIME
        """))
        print("  Added column: last_check to repositories")

    # Check if last_compact column exists
    try:
        connection.execute(text("""
            SELECT last_compact FROM repositories LIMIT 1
        """))
        print("  Skipped (exists): last_compact column")
    except Exception:
        connection.execute(text("""
            ALTER TABLE repositories ADD COLUMN last_compact DATETIME
        """))
        print("  Added column: last_compact to repositories")

    print("✓ Migration 015: Added last_check and last_compact to repositories")

def downgrade(connection):
    """Remove last_check and last_compact columns from repositories table"""

    # SQLite doesn't support DROP COLUMN directly, would need table recreation
    # For now, just log that downgrade would be complex
    print("⚠ Migration 015 downgrade: SQLite doesn't support DROP COLUMN")
    print("  Manual intervention required to remove last_check and last_compact columns")
