"""Add missing mqtt_base_topic column to system_settings

Migration 071 added all mqtt_* columns except mqtt_base_topic, causing a
runtime error for anyone who upgraded to 1.72.0. This migration adds the
missing column for existing databases; 071 was also patched to include it
for fresh installs.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN mqtt_base_topic TEXT DEFAULT 'borg-ui' NOT NULL
        """))
        db.commit()
        logger.info("Migration 072_add_mqtt_base_topic completed successfully")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("mqtt_base_topic column already exists, skipping")
        else:
            raise


def downgrade(db):
    logger.warning("Downgrade not supported: mqtt_base_topic column remains in SQLite")
