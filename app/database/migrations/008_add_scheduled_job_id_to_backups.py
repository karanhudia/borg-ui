"""
Migration 008: Add scheduled_job_id to backup_jobs table

This migration adds a foreign key field to track which backups were triggered by scheduled jobs.
- scheduled_job_id: NULL for manual backups, references scheduled_jobs.id for automated backups
"""

from sqlalchemy import text

def upgrade(connection):
    """Add scheduled_job_id column to backup_jobs table"""

    # Check if column exists
    result = connection.execute(text("PRAGMA table_info(backup_jobs)"))
    existing_columns = {row[1] for row in result}

    if "scheduled_job_id" not in existing_columns:
        connection.execute(text("""
            ALTER TABLE backup_jobs
            ADD COLUMN scheduled_job_id INTEGER DEFAULT NULL
        """))
        print("  Added column: scheduled_job_id")
    else:
        print("  Skipped (exists): scheduled_job_id")

    print("✓ Migration 008: Added scheduled_job_id to backup_jobs")

def downgrade(connection):
    """Remove scheduled_job_id column from backup_jobs table"""

    connection.execute(text("""
        ALTER TABLE backup_jobs
        DROP COLUMN IF EXISTS scheduled_job_id
    """))

    print("✓ Migration 008 rolled back: Removed scheduled_job_id from backup_jobs")
