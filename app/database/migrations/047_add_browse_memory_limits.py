"""Add browse memory limit settings to prevent OOM crashes"""

from sqlalchemy import text


def upgrade(connection):
    """Add browse memory limit columns to system_settings table"""
    # Check if columns already exist (SQLite compatible)
    result = connection.execute(
        text("PRAGMA table_info(system_settings)")
    ).fetchall()

    column_names = [row[1] for row in result]

    if 'browse_max_items' not in column_names:
        # Maximum number of items to load into memory when browsing archives
        connection.execute(text(
            "ALTER TABLE system_settings ADD COLUMN browse_max_items INTEGER DEFAULT 1000000 NOT NULL"
        ))
        print("✓ Added browse_max_items column to system_settings table (default: 1,000,000)")
    else:
        print("✓ browse_max_items column already exists in system_settings table")

    if 'browse_max_memory_mb' not in column_names:
        # Maximum estimated memory usage (MB) when browsing archives
        connection.execute(text(
            "ALTER TABLE system_settings ADD COLUMN browse_max_memory_mb INTEGER DEFAULT 1024 NOT NULL"
        ))
        print("✓ Added browse_max_memory_mb column to system_settings table (default: 1024 MB)")
    else:
        print("✓ browse_max_memory_mb column already exists in system_settings table")


def downgrade(connection):
    """Remove browse memory limit columns from system_settings table"""
    # SQLite doesn't support DROP COLUMN easily
    # For now, just acknowledge it can't be removed
    print("✓ Downgrade skipped - SQLite doesn't support DROP COLUMN")
