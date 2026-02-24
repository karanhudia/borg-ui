"""Add source_size_timeout to system_settings table

This migration adds the source_size_timeout integer field to allow
configuring the timeout for du-based source size calculation during
backups. Large datasets (e.g., 10TB+) can take much longer than the
previous hardcoded 120-second limit to fully traverse.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add source_size_timeout to system_settings"""
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN source_size_timeout INTEGER DEFAULT NULL
        """))
        logger.info("Added source_size_timeout column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("source_size_timeout column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 070_add_source_size_timeout completed successfully")


def downgrade(db):
    """Remove source_size_timeout column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - column will remain")
