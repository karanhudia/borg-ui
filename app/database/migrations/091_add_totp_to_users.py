"""Add TOTP fields to users."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    statements = [
        (
            "totp_secret_encrypted",
            "ALTER TABLE users ADD COLUMN totp_secret_encrypted VARCHAR",
        ),
        (
            "totp_enabled",
            "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT 0 NOT NULL",
        ),
        (
            "totp_enabled_at",
            "ALTER TABLE users ADD COLUMN totp_enabled_at DATETIME",
        ),
        (
            "totp_recovery_codes_hashes",
            "ALTER TABLE users ADD COLUMN totp_recovery_codes_hashes TEXT",
        ),
    ]

    for column_name, sql in statements:
        try:
            db.execute(text(sql))
            logger.info("Added users column", column=column_name)
        except Exception as e:
            if (
                "duplicate column" in str(e).lower()
                or "already exists" in str(e).lower()
            ):
                logger.info("users column already exists", column=column_name)
            else:
                raise

    db.commit()
    logger.info("Migration 091_add_totp_to_users completed")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — columns will remain")
