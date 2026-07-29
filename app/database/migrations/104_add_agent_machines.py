"""Add Borg UI managed agent machine tables."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    db.execute(
        text("""
        CREATE TABLE IF NOT EXISTS agent_machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR NOT NULL,
            agent_id VARCHAR NOT NULL UNIQUE,
            token_hash VARCHAR NOT NULL,
            token_prefix VARCHAR(20) NOT NULL,
            hostname VARCHAR,
            os VARCHAR,
            arch VARCHAR,
            agent_version VARCHAR,
            borg_versions JSON,
            capabilities JSON,
            labels JSON,
            status VARCHAR NOT NULL DEFAULT 'pending',
            last_seen_at DATETIME,
            last_error TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """)
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_machines_agent_id "
            "ON agent_machines(agent_id)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_machines_token_prefix "
            "ON agent_machines(token_prefix)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_machines_status "
            "ON agent_machines(status)"
        )
    )

    db.execute(
        text("""
        CREATE TABLE IF NOT EXISTS agent_enrollment_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR NOT NULL,
            token_hash VARCHAR NOT NULL,
            token_prefix VARCHAR(20) NOT NULL,
            created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            expires_at DATETIME NOT NULL,
            used_at DATETIME,
            used_by_agent_id INTEGER REFERENCES agent_machines(id) ON DELETE SET NULL,
            revoked_at DATETIME,
            created_at DATETIME NOT NULL
        )
        """)
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_enrollment_tokens_token_prefix "
            "ON agent_enrollment_tokens(token_prefix)"
        )
    )
    db.commit()
    logger.info("Migration 104_add_agent_machines completed")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite - agent tables will remain")
