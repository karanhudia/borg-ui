"""Add managed_agents_beta_enabled to system_settings."""

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


def upgrade(db):
    try:
        db.execute(
            text(
                """
                ALTER TABLE system_settings
                ADD COLUMN managed_agents_beta_enabled BOOLEAN DEFAULT 0 NOT NULL
                """
            )
        )
        db.commit()
        logger.info("Added system_settings.managed_agents_beta_enabled column")
    except Exception as e:
        db.rollback()
        if "duplicate column name" in str(e).lower():
            logger.info("system_settings.managed_agents_beta_enabled already exists")
            return
        raise


def downgrade(db):
    logger.info("SQLite downgrade not supported for managed_agents_beta_enabled")
