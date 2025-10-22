"""
Migration 006: Add scheduled_jobs table

This migration creates the scheduled_jobs table to support cron-based
automated backups.
"""

from sqlalchemy import text

def upgrade(connection):
    """Create scheduled_jobs table"""

    # Check if table exists
    result = connection.execute(text("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='scheduled_jobs'
    """))

    if result.fetchone() is None:
        connection.execute(text("""
            CREATE TABLE scheduled_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL UNIQUE,
                cron_expression VARCHAR NOT NULL,
                repository VARCHAR,
                config_file VARCHAR,
                enabled BOOLEAN DEFAULT 1,
                last_run DATETIME,
                next_run DATETIME,
                description TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME
            )
        """))

        # Create indexes
        connection.execute(text("""
            CREATE INDEX ix_scheduled_jobs_name ON scheduled_jobs (name)
        """))

        connection.execute(text("""
            CREATE INDEX ix_scheduled_jobs_enabled ON scheduled_jobs (enabled)
        """))

        connection.execute(text("""
            CREATE INDEX ix_scheduled_jobs_next_run ON scheduled_jobs (next_run)
        """))

        print("  Created table: scheduled_jobs")
        print("  Created indexes: ix_scheduled_jobs_name, ix_scheduled_jobs_enabled, ix_scheduled_jobs_next_run")
    else:
        print("  Skipped (exists): scheduled_jobs table")

    print("✓ Migration 006: Added scheduled_jobs table")

def downgrade(connection):
    """Drop scheduled_jobs table"""

    connection.execute(text("DROP TABLE IF EXISTS scheduled_jobs"))
    print("✓ Migration 006 rolled back: Removed scheduled_jobs table")
