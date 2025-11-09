"""
Migration 014: Add check_jobs and compact_jobs tables

This migration creates tables to track check and compact operations
with progress tracking support for long-running operations.
"""

from sqlalchemy import text

def upgrade(connection):
    """Create check_jobs and compact_jobs tables"""

    # Create check_jobs table
    result = connection.execute(text("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='check_jobs'
    """))

    if result.fetchone() is None:
        connection.execute(text("""
            CREATE TABLE check_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id INTEGER NOT NULL,
                status VARCHAR DEFAULT 'pending',
                started_at DATETIME,
                completed_at DATETIME,
                progress INTEGER DEFAULT 0,
                progress_message VARCHAR,
                error_message TEXT,
                logs TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (repository_id) REFERENCES repositories (id)
            )
        """))

        # Create indexes for common queries
        connection.execute(text("""
            CREATE INDEX ix_check_jobs_id ON check_jobs (id)
        """))

        connection.execute(text("""
            CREATE INDEX ix_check_jobs_status ON check_jobs (status)
        """))

        connection.execute(text("""
            CREATE INDEX ix_check_jobs_repository_id ON check_jobs (repository_id)
        """))

        print("  Created table: check_jobs")
        print("  Created indexes: ix_check_jobs_id, ix_check_jobs_status, ix_check_jobs_repository_id")
    else:
        print("  Skipped (exists): check_jobs table")

    # Create compact_jobs table
    result = connection.execute(text("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='compact_jobs'
    """))

    if result.fetchone() is None:
        connection.execute(text("""
            CREATE TABLE compact_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id INTEGER NOT NULL,
                status VARCHAR DEFAULT 'pending',
                started_at DATETIME,
                completed_at DATETIME,
                progress INTEGER DEFAULT 0,
                progress_message VARCHAR,
                error_message TEXT,
                logs TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (repository_id) REFERENCES repositories (id)
            )
        """))

        # Create indexes for common queries
        connection.execute(text("""
            CREATE INDEX ix_compact_jobs_id ON compact_jobs (id)
        """))

        connection.execute(text("""
            CREATE INDEX ix_compact_jobs_status ON compact_jobs (status)
        """))

        connection.execute(text("""
            CREATE INDEX ix_compact_jobs_repository_id ON compact_jobs (repository_id)
        """))

        print("  Created table: compact_jobs")
        print("  Created indexes: ix_compact_jobs_id, ix_compact_jobs_status, ix_compact_jobs_repository_id")
    else:
        print("  Skipped (exists): compact_jobs table")

    print("✓ Migration 014: Added check_jobs and compact_jobs tables")

def downgrade(connection):
    """Drop check_jobs and compact_jobs tables"""

    connection.execute(text("DROP TABLE IF EXISTS check_jobs"))
    connection.execute(text("DROP TABLE IF EXISTS compact_jobs"))
    print("✓ Migration 014 rolled back: Removed check_jobs and compact_jobs tables")
