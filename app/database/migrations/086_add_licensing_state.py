"""Add licensing_state table for local entitlement storage"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(
            text("""
            CREATE TABLE IF NOT EXISTS licensing_state (
                id INTEGER PRIMARY KEY,
                instance_id VARCHAR NOT NULL UNIQUE,
                plan VARCHAR NOT NULL DEFAULT 'community',
                status VARCHAR NOT NULL DEFAULT 'none',
                is_trial BOOLEAN NOT NULL DEFAULT 0,
                trial_consumed BOOLEAN NOT NULL DEFAULT 0,
                entitlement_id VARCHAR UNIQUE,
                key_id VARCHAR,
                customer_id VARCHAR,
                license_id VARCHAR,
                max_users INTEGER,
                issued_at DATETIME,
                starts_at DATETIME,
                expires_at DATETIME,
                last_refresh_at DATETIME,
                last_refresh_error TEXT,
                payload_json JSON,
                signature TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
        """)
        )
        logger.info("Ensured licensing_state table exists")
    except Exception as e:
        logger.error("Failed to create licensing_state table", error=str(e))
        raise

    db.commit()
    logger.info("Migration 086_add_licensing_state completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — licensing_state will remain")
