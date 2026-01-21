"""Add bypass_lock to repositories table

This migration adds the bypass_lock boolean field for observe-only repos
that need read-only storage access (adds --bypass-lock to borg commands).
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add bypass_lock to repositories"""
    try:
        db.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN bypass_lock BOOLEAN DEFAULT 0
        """))
        logger.info("Added bypass_lock column to repositories")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("bypass_lock column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 055_add_bypass_lock completed successfully")


def downgrade(db):
    """Remove bypass_lock column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - column will remain")
