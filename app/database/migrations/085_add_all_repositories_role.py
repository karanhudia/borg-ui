"""
Add all_repositories_role to users for persistent repository-wide assignments.
"""
from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN all_repositories_role VARCHAR"))
        logger.info("Added users.all_repositories_role column")
    except Exception as exc:
        if "duplicate column" in str(exc).lower():
            logger.info("users.all_repositories_role already exists")
        else:
            raise

    db.commit()


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — column will remain")
