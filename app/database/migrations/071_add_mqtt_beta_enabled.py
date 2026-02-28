"""Add MQTT settings columns to system_settings

The SystemSettings model now exposes the MQTT beta flag and connection
settings, so the schema needs every `mqtt_*` column to prevent runtime errors.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def _add_column(db, column_name, ddl):
    try:
        db.execute(text(ddl))
        logger.info("Added %s column to system_settings", column_name)
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("%s column already exists", column_name)
        else:
            raise


def upgrade(db):
    """Add every mqtt_* column that the model now exposes."""
    columns = [
        ("mqtt_beta_enabled", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_beta_enabled BOOLEAN DEFAULT 0 NOT NULL
        """),
        ("mqtt_enabled", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_enabled BOOLEAN DEFAULT 0 NOT NULL
        """),
        ("mqtt_broker_url", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_broker_url TEXT
        """),
        ("mqtt_broker_port", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_broker_port INTEGER DEFAULT 1883 NOT NULL
        """),
        ("mqtt_username", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_username TEXT
        """),
        ("mqtt_password", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_password TEXT
        """),
        ("mqtt_client_id", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_client_id TEXT DEFAULT 'borg-ui' NOT NULL
        """),
        ("mqtt_qos", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_qos INTEGER DEFAULT 1 NOT NULL
        """),
        ("mqtt_retain", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_retain BOOLEAN DEFAULT 0 NOT NULL
        """),
        ("mqtt_tls_enabled", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_tls_enabled BOOLEAN DEFAULT 0 NOT NULL
        """),
        ("mqtt_tls_ca_cert", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_tls_ca_cert TEXT
        """),
        ("mqtt_tls_client_cert", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_tls_client_cert TEXT
        """),
        ("mqtt_tls_client_key", """
            ALTER TABLE system_settings
            ADD COLUMN mqtt_tls_client_key TEXT
        """),
    ]

    for name, ddl in columns:
        _add_column(db, name, ddl)

    db.commit()
    logger.info("Migration 070_add_mqtt_beta_enabled completed successfully")


def downgrade(db):
    """Downgrade is not supported on SQLite, keep existing columns."""
    logger.warning(
        "Downgrade not supported: mqtt_* columns remain in SQLite"
    )
