"""
Migration 007: Add size-based progress fields to backup_jobs table

This migration adds fields to support accurate progress tracking and ETA calculation:
- total_expected_size: Total size of source directories (calculated before backup)
- estimated_time_remaining: ETA in seconds based on backup speed
"""

from sqlalchemy import text

def upgrade(connection):
    """Add total_expected_size and estimated_time_remaining columns"""

    # Check if columns exist
    result = connection.execute(text("PRAGMA table_info(backup_jobs)"))
    existing_columns = {row[1] for row in result}

    if "total_expected_size" not in existing_columns:
        connection.execute(text("""
            ALTER TABLE backup_jobs
            ADD COLUMN total_expected_size BIGINT DEFAULT 0
        """))
        print("  Added column: total_expected_size")
    else:
        print("  Skipped (exists): total_expected_size")

    if "estimated_time_remaining" not in existing_columns:
        connection.execute(text("""
            ALTER TABLE backup_jobs
            ADD COLUMN estimated_time_remaining INTEGER DEFAULT 0
        """))
        print("  Added column: estimated_time_remaining")
    else:
        print("  Skipped (exists): estimated_time_remaining")

    print("✓ Migration 007: Added size-based progress fields to backup_jobs")

def downgrade(connection):
    """Remove total_expected_size and estimated_time_remaining columns"""

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS total_expected_size
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS estimated_time_remaining
    """))

    print("✓ Migration 007 rolled back: Removed size-based progress fields from backup_jobs")
