"""
Migration 004: Add detailed progress fields to backup_jobs table

This migration adds fields to store real-time progress information from
Borg's JSON output including file counts, sizes, and current file being processed.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add progress tracking fields to backup_jobs table"""

    # Add fields for tracking detailed backup progress
    connection.execute(text("""
        ALTER TABLE backup_jobs
        ADD COLUMN IF NOT EXISTS original_size BIGINT DEFAULT 0
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        ADD COLUMN IF NOT EXISTS compressed_size BIGINT DEFAULT 0
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        ADD COLUMN IF NOT EXISTS deduplicated_size BIGINT DEFAULT 0
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        ADD COLUMN IF NOT EXISTS nfiles INTEGER DEFAULT 0
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        ADD COLUMN IF NOT EXISTS current_file TEXT
    """))

    connection.execute(text("""
        ALTER TABLE backup_jobs
        ADD COLUMN IF NOT EXISTS progress_percent REAL DEFAULT 0
    """))

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
