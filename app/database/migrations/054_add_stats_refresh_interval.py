"""Add stats_refresh_interval_minutes to system_settings table

This migration adds the stats_refresh_interval_minutes setting for
configuring how often repository stats are automatically refreshed.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add stats_refresh_interval_minutes to system_settings"""
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN stats_refresh_interval_minutes INTEGER DEFAULT 60
        """))
        logger.info("Added stats_refresh_interval_minutes column")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("stats_refresh_interval_minutes column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 054_add_stats_refresh_interval completed successfully")


def downgrade(db):
    """Remove stats_refresh_interval_minutes column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - column will remain")
