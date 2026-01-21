"""Add operation timeout settings to system_settings table

This migration adds configurable timeouts for various borg operations
to support large repositories that may need more time.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add timeout columns to system_settings"""
    try:
        # Add mount_timeout column
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN mount_timeout INTEGER DEFAULT 120
        """))
        logger.info("Added mount_timeout column")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("mount_timeout column already exists")
        else:
            raise

    try:
        # Add info_timeout column
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN info_timeout INTEGER DEFAULT 600
        """))
        logger.info("Added info_timeout column")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("info_timeout column already exists")
        else:
            raise

    try:
        # Add list_timeout column
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN list_timeout INTEGER DEFAULT 600
        """))
        logger.info("Added list_timeout column")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("list_timeout column already exists")
        else:
            raise

    try:
        # Add init_timeout column
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN init_timeout INTEGER DEFAULT 300
        """))
        logger.info("Added init_timeout column")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("init_timeout column already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 053_add_operation_timeouts completed successfully")


def downgrade(db):
    """Remove timeout columns (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("Downgrade not fully supported for SQLite - columns will remain")
