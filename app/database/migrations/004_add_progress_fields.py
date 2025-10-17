"""
Migration 004: Add detailed progress fields to backup_jobs table

This migration adds fields to store real-time progress information from
Borg's JSON output including file counts, sizes, and current file being processed.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add progress tracking fields to backup_jobs table"""

    # SQLite doesn't support IF NOT EXISTS in ALTER TABLE
    # We need to check if columns exist first
    columns_to_add = [
        ("original_size", "BIGINT DEFAULT 0"),
        ("compressed_size", "BIGINT DEFAULT 0"),
        ("deduplicated_size", "BIGINT DEFAULT 0"),
        ("nfiles", "INTEGER DEFAULT 0"),
        ("current_file", "TEXT"),
        ("progress_percent", "REAL DEFAULT 0")
    ]

    # Get existing columns
    result = connection.execute(text("PRAGMA table_info(backup_jobs)"))
    existing_columns = {row[1] for row in result}

    # Add only missing columns
    for column_name, column_def in columns_to_add:
        if column_name not in existing_columns:
            connection.execute(text(f"""
                ALTER TABLE backup_jobs
                ADD COLUMN {column_name} {column_def}
            """))
            print(f"  Added column: {column_name}")
        else:
            print(f"  Skipped (exists): {column_name}")

    print("✓ Migration 004: Added detailed progress fields to backup_jobs")

def downgrade(connection):
    """Remove progress tracking fields from backup_jobs table"""

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS original_size
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS compressed_size
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS deduplicated_size
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS nfiles
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS current_file
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS progress_percent
    """))

    print("✓ Migration 004 rolled back: Removed progress fields from backup_jobs")
