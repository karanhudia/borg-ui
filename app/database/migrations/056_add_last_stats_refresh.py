"""Add last_stats_refresh to system_settings table

This migration adds a timestamp to track when stats were last refreshed.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add last_stats_refresh to system_settings"""
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN last_stats_refresh DATETIME
        """))
        logger.info("Added last_stats_refresh column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("last_stats_refresh column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 056_add_last_stats_refresh completed successfully")


def downgrade(db):
    """Remove last_stats_refresh column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - column will remain")
