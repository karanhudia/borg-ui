"""
Migration 009: Add restore_jobs table

This migration creates the restore_jobs table to track restore operations
with progress tracking support.
"""

from sqlalchemy import text

def upgrade(connection):
    """Create restore_jobs table"""

    # Check if table exists
    result = connection.execute(text("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='restore_jobs'
    """))

    if result.fetchone() is None:
        connection.execute(text("""
            CREATE TABLE restore_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository VARCHAR,
                archive VARCHAR,
                destination VARCHAR,
                status VARCHAR DEFAULT 'pending',
                started_at DATETIME,
                completed_at DATETIME,
                progress INTEGER DEFAULT 0,
                error_message TEXT,
                logs TEXT,
                nfiles INTEGER DEFAULT 0,
                current_file TEXT,
                progress_percent FLOAT DEFAULT 0.0,
                created_at DATETIME NOT NULL
            )
        """))

        # Create indexes for common queries
        connection.execute(text("""
            CREATE INDEX ix_restore_jobs_id ON restore_jobs (id)
        """))

        connection.execute(text("""
            CREATE INDEX ix_restore_jobs_status ON restore_jobs (status)
        """))

        print("  Created table: restore_jobs")
        print("  Created indexes: ix_restore_jobs_id, ix_restore_jobs_status")
    else:
        print("  Skipped (exists): restore_jobs table")

    print("✓ Migration 009: Added restore_jobs table")

def downgrade(connection):
    """Drop restore_jobs table"""

    connection.execute(text("DROP TABLE IF EXISTS restore_jobs"))
    print("✓ Migration 009 rolled back: Removed restore_jobs table")
