"""
Migration 067: Add CASCADE delete to script_executions.backup_job_id foreign key

When a backup job is deleted, automatically delete all related script executions.
This prevents foreign key constraint errors when deleting backup jobs from the activity feed.

Since SQLite doesn't support modifying foreign keys directly, we need to:
1. Create a new table with the correct foreign key constraint
2. Copy all data from the old table
3. Drop the old table
4. Rename the new table
"""

import structlog
from sqlalchemy import text

logger = structlog.get_logger()


def upgrade(db):
    """Add CASCADE delete to backup_job_id foreign key"""
    try:
        logger.info("Adding CASCADE delete to script_executions.backup_job_id foreign key")

        # First, check if the table exists
        result = db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='script_executions'"
        ))
        if not result.fetchone():
            logger.info("script_executions table does not exist, skipping migration")
            return

        # Create new table with CASCADE delete
        db.execute(text("""
            CREATE TABLE script_executions_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                script_id INTEGER NOT NULL,
                repository_id INTEGER,
                backup_job_id INTEGER,
                hook_type VARCHAR(50),
                status VARCHAR(50) NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,
                execution_time FLOAT,
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                error_message TEXT,
                triggered_by VARCHAR(50),
                triggered_by_user_id INTEGER,
                FOREIGN KEY(script_id) REFERENCES scripts (id),
                FOREIGN KEY(repository_id) REFERENCES repositories (id),
                FOREIGN KEY(backup_job_id) REFERENCES backup_jobs (id) ON DELETE CASCADE,
                FOREIGN KEY(triggered_by_user_id) REFERENCES users (id)
            )
        """))

        # Copy data from old table to new table
        db.execute(text("""
            INSERT INTO script_executions_new
            SELECT * FROM script_executions
        """))

        # Drop old table
        db.execute(text("DROP TABLE script_executions"))

        # Rename new table to original name
        db.execute(text("ALTER TABLE script_executions_new RENAME TO script_executions"))

        # Recreate indexes
        db.execute(text("CREATE INDEX ix_script_executions_script_id ON script_executions (script_id)"))
        db.execute(text("CREATE INDEX ix_script_executions_repository_id ON script_executions (repository_id)"))
        db.execute(text("CREATE INDEX ix_script_executions_backup_job_id ON script_executions (backup_job_id)"))

        db.commit()

        logger.info("✓ Added CASCADE delete to script_executions.backup_job_id foreign key")

    except Exception as e:
        db.rollback()
        logger.error("Failed to add CASCADE delete to script_executions", error=str(e))
        raise
