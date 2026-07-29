"""
Add metrics settings to system_settings.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    columns = [
        (
            "metrics_enabled",
            "ALTER TABLE system_settings ADD COLUMN metrics_enabled BOOLEAN DEFAULT 0",
        ),
        (
            "metrics_require_auth",
            "ALTER TABLE system_settings ADD COLUMN metrics_require_auth BOOLEAN DEFAULT 0",
        ),
        (
            "metrics_token",
            "ALTER TABLE system_settings ADD COLUMN metrics_token VARCHAR",
        ),
    ]

    for column_name, statement in columns:
        try:
            db.execute(text(statement))
            logger.info("Added system_settings column", column=column_name)
        except Exception as e:
            if "duplicate column" in str(e).lower():
                logger.info("Column already exists", column=column_name)
            else:
                raise

    db.commit()
    logger.info("Migration 088_add_metrics_settings completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — columns will remain")
