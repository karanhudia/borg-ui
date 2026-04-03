# app/database/migrations/081_add_role_tokens_permissions.py
"""
Add role column to users (replacing is_admin boolean),
and create api_tokens table.
"""
from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    # 1. Add role column to users
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'viewer'"))
        logger.info("Added role column to users")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("role column already exists on users")
        else:
            raise

    # 2. Migrate is_admin → role
    db.execute(text("UPDATE users SET role = 'admin' WHERE is_admin = 1"))
    db.execute(text("UPDATE users SET role = 'viewer' WHERE is_admin = 0 OR is_admin IS NULL"))
    logger.info("Migrated is_admin values to role column")

    # 3. Create api_tokens table
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR NOT NULL,
                token_hash VARCHAR NOT NULL,
                prefix VARCHAR(12) NOT NULL,
                created_at DATETIME NOT NULL,
                last_used_at DATETIME
            )
        """))
        logger.info("Created api_tokens table")
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info("api_tokens table already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 081_add_role_tokens_permissions completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — schema changes will remain")
