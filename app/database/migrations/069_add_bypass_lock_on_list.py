"""Add bypass_lock_on_list to system_settings table

This migration adds the bypass_lock_on_list boolean field as a beta feature
to enable --bypass-lock flag on all borg list commands across the application.
This helps prevent lock contention issues when concurrent read operations
(like info + list) run simultaneously on SSH repositories.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add bypass_lock_on_list to system_settings"""
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN bypass_lock_on_list BOOLEAN DEFAULT 0 NOT NULL
        """))
        logger.info("Added bypass_lock_on_list column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("bypass_lock_on_list column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 069_add_bypass_lock_on_list completed successfully")


def downgrade(db):
    """Remove bypass_lock_on_list column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - column will remain")
