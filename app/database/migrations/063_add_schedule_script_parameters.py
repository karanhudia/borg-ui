"""
Migration: Add script parameters to scheduled_jobs table

This migration adds support for passing parameters to schedule-level scripts:
- pre_backup_script_parameters (JSON)
- post_backup_script_parameters (JSON)

These allow users to configure script parameters when setting up scheduled backups,
similar to how they can configure parameters for repository-level scripts.

Created: 2026-02-04
"""

import structlog
from sqlalchemy import text

logger = structlog.get_logger()

def upgrade(db):
    """Add script parameter columns to scheduled_jobs table"""

    logger.info("Adding script parameter columns to scheduled_jobs table...")

    try:
        # Add pre_backup_script_parameters column
        db.execute(text("""
            ALTER TABLE scheduled_jobs
            ADD COLUMN pre_backup_script_parameters TEXT
        """))

        # Add post_backup_script_parameters column
        db.execute(text("""
            ALTER TABLE scheduled_jobs
            ADD COLUMN post_backup_script_parameters TEXT
        """))

        db.commit()
        logger.info("Script parameter columns added successfully")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            logger.info("Script parameter columns already exist, skipping")
        else:
            logger.error(f"Failed to add script parameter columns: {e}")
            raise


def downgrade(db):
    """Remove script parameter columns from scheduled_jobs table"""

    logger.info("Removing script parameter columns from scheduled_jobs table...")

    try:
        db.execute(text("""
            ALTER TABLE scheduled_jobs
            DROP COLUMN IF EXISTS pre_backup_script_parameters
        """))

        db.execute(text("""
            ALTER TABLE scheduled_jobs
            DROP COLUMN IF EXISTS post_backup_script_parameters
        """))

        db.commit()
        logger.info("Script parameter columns removed successfully")
    except Exception as e:
        logger.error(f"Failed to remove script parameter columns: {e}")
        raise
