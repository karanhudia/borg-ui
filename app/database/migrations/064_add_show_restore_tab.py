"""Add show_restore_tab to system_settings table

This migration adds the show_restore_tab boolean field as a beta feature
to allow users to show/hide the legacy Restore tab in the navigation menu.
Restore functionality has been integrated into the Archives page, but this
option allows users to access the dedicated Restore tab if preferred.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add show_restore_tab to system_settings"""
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN show_restore_tab BOOLEAN DEFAULT 0 NOT NULL
        """))
        logger.info("Added show_restore_tab column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("show_restore_tab column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 064_add_show_restore_tab completed successfully")


def downgrade(db):
    """Remove show_restore_tab column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - column will remain")
