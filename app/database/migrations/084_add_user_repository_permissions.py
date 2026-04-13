"""
Create user_repository_permissions table for repository-scoped RBAC.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_repository_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    role VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL,
                    UNIQUE(user_id, repository_id)
                )
                """
            )
        )
        logger.info("Created user_repository_permissions table")
        db.commit()
    except Exception as exc:
        if "already exists" in str(exc).lower():
            logger.info("user_repository_permissions table already exists")
        else:
            raise


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — schema changes will remain")
