"""
Migration 005: Add backup_speed field to backup_jobs table

This migration adds a field to store real-time backup speed in MB/s,
calculated from original_size and elapsed time.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add backup_speed field to backup_jobs table"""

    # Check if column exists
    result = connection.execute(text("PRAGMA table_info(backup_jobs)"))
    existing_columns = {row[1] for row in result}

    if "backup_speed" not in existing_columns:
        connection.execute(text("""
            ALTER TABLE backup_jobs
            ADD COLUMN backup_speed REAL DEFAULT 0.0
        """))
        print("  Added column: backup_speed")
    else:
        print("  Skipped (exists): backup_speed")

    print("✓ Migration 005: Added backup_speed field to backup_jobs")

def downgrade(connection):
    """Remove backup_speed field from backup_jobs table"""

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS backup_speed
    """))

    print("✓ Migration 005 rolled back: Removed backup_speed field from backup_jobs")
