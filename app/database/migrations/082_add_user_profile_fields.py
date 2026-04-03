"""
Add optional profile fields to users for account personalization.
"""
from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    columns = [
        ("full_name", "ALTER TABLE users ADD COLUMN full_name VARCHAR"),
        ("organization_name", "ALTER TABLE users ADD COLUMN organization_name VARCHAR"),
        (
            "profile_type",
            "ALTER TABLE users ADD COLUMN profile_type VARCHAR DEFAULT 'individual'",
        ),
    ]

    for column_name, statement in columns:
        try:
            db.execute(text(statement))
            logger.info("Added users column", column=column_name)
        except Exception as e:
            if "duplicate column" in str(e).lower():
                logger.info("Users column already exists", column=column_name)
            else:
                raise

    db.commit()
    logger.info("Migration 082_add_user_profile_fields completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — schema changes will remain")
