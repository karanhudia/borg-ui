"""
Migration 013: Add maintenance_status to backup_jobs

This migration adds a field to track the status of maintenance operations
(prune and compact) that run after scheduled backups complete.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add maintenance_status field to backup_jobs table"""

    # Check if column already exists
    result = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='backup_jobs'
    """))

    table_sql = result.fetchone()
    if table_sql:
        table_def = table_sql[0]

        # Add maintenance_status column if it doesn't exist
        if 'maintenance_status' not in table_def:
            connection.execute(text("""
                ALTER TABLE backup_jobs
                ADD COLUMN maintenance_status TEXT
            """))
            print("  Added column: maintenance_status")
        else:
            print("  Skipped (exists): maintenance_status column")

    print("✓ Migration 013: Added maintenance_status to backup_jobs")

def downgrade(connection):
    """Remove maintenance_status field from backup_jobs table"""

    # SQLite doesn't support DROP COLUMN directly
    # Would need to recreate table without this column
    # For now, we'll leave it (it defaults to NULL)

    print("✓ Migration 013 rollback: maintenance_status column remains (set to NULL)")
