"""Add borg2_fast_browse_beta_enabled to system_settings."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(
            text(
                """
                ALTER TABLE system_settings
                ADD COLUMN borg2_fast_browse_beta_enabled BOOLEAN DEFAULT 0 NOT NULL
                """
            )
        )
        logger.info("Added system_settings.borg2_fast_browse_beta_enabled column")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            logger.info("system_settings.borg2_fast_browse_beta_enabled already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 090_add_borg2_fast_browse_beta_enabled completed")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — column will remain")
