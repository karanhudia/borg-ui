"""Add plan column to system_settings

The plan column stores the current feature plan tier (community, standard, pro, etc.)
and controls which features are available to the user.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN plan VARCHAR DEFAULT 'pro'
        """))
        logger.info("Added plan column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("plan column already exists on system_settings")
        else:
            raise

    db.commit()
    logger.info("Migration 080_add_plan completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — columns will remain")
