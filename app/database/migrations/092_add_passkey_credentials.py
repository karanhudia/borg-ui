"""Add passkey credentials table."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS passkey_credentials (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR NOT NULL,
                credential_id VARCHAR NOT NULL UNIQUE,
                public_key TEXT NOT NULL,
                sign_count INTEGER NOT NULL DEFAULT 0,
                transports TEXT,
                device_type VARCHAR,
                backed_up BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                last_used_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_passkey_credentials_user_id ON passkey_credentials(user_id)"
        )
    )
    db.commit()
    logger.info("Migration 092_add_passkey_credentials completed")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — table will remain")
