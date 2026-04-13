"""Add archive_name column to backup_jobs table"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(text("ALTER TABLE backup_jobs ADD COLUMN archive_name VARCHAR"))
        logger.info("Added backup_jobs.archive_name column")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            logger.info("Column archive_name already exists on backup_jobs")
        else:
            raise

    db.commit()
    logger.info("Migration 089_add_backup_job_archive_name completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — column will remain")
