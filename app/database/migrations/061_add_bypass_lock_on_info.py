"""Add bypass_lock_on_info to system_settings table

This migration adds the bypass_lock_on_info boolean field as a beta feature
to enable --bypass-lock flag on all borg info commands across the application.
This helps prevent lock contention issues on SSH repositories.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add bypass_lock_on_info to system_settings"""
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN bypass_lock_on_info BOOLEAN DEFAULT 0 NOT NULL
        """))
        logger.info("Added bypass_lock_on_info column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("bypass_lock_on_info column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 061_add_bypass_lock_on_info completed successfully")


def downgrade(db):
    """Remove bypass_lock_on_info column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - column will remain")
