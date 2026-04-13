"""
Add deployment_type and enterprise_name to system_settings.

Moves the deployment identity concept (individual vs enterprise) from
per-user fields to a system-level setting. The old user columns
(profile_type, organization_name) are left in the database schema
for SQLite compatibility but are removed from the ORM model.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    columns = [
        (
            "deployment_type",
            "ALTER TABLE system_settings ADD COLUMN deployment_type VARCHAR DEFAULT 'individual'",
        ),
        (
            "enterprise_name",
            "ALTER TABLE system_settings ADD COLUMN enterprise_name VARCHAR",
        ),
    ]

    for column_name, statement in columns:
        try:
            db.execute(text(statement))
            logger.info("Added system_settings column", column=column_name)
        except Exception as e:
            if "duplicate column" in str(e).lower():
                logger.info("Column already exists", column=column_name)
            else:
                raise

    db.commit()
    logger.info("Migration 083_add_deployment_profile completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — columns will remain")
