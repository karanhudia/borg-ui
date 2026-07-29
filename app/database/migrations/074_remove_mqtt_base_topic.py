"""Remove mqtt_base_topic column from system_settings

The mqtt_base_topic field is being removed from the SystemSettings model
as it's no longer needed for MQTT functionality.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(
            text("""
            ALTER TABLE system_settings
            DROP COLUMN mqtt_base_topic
        """)
        )
        db.commit()
        logger.info("Migration 074_remove_mqtt_base_topic completed successfully")
    except Exception as e:
        if "cannot drop column" in str(e).lower() or "no such column" in str(e).lower():
            logger.info("mqtt_base_topic column does not exist, skipping")
        else:
            raise


def downgrade(db):
    logger.warning(
        "Downgrade not supported: mqtt_base_topic column removal is irreversible"
    )
