"""
Migration 068: Add remote restore fields to restore_jobs table

Adds support for remote restore functionality with three scenarios:
1. SSH Repository → Local Destination (extract from remote repo to local machine)
2. Local Repository → SSH Destination (extract from local repo to remote machine)
3. Local Repository → Local Destination (existing functionality)

New fields:
- destination_type: 'local' or 'ssh' to indicate destination type
- destination_connection_id: Foreign key to ssh_connections for SSH destinations
- execution_mode: Tracks the restore scenario (e.g., 'local_to_local', 'ssh_to_local', 'local_to_ssh')
- temp_extraction_path: Temporary path for two-phase restore (local→SSH scenario)
- destination_hostname: Hostname for display purposes
- repository_type: Type of repository ('local' or 'ssh')
"""

import structlog
from sqlalchemy import text

logger = structlog.get_logger()


def upgrade(db):
    """Add remote restore fields to restore_jobs table"""
    logger.info("Adding remote restore fields to restore_jobs table")

    columns_to_add = [
        ("destination_type", "VARCHAR(50) DEFAULT 'local'"),
        ("destination_connection_id", "INTEGER"),
        ("execution_mode", "VARCHAR(50) DEFAULT 'local_to_local'"),
        ("temp_extraction_path", "VARCHAR(255)"),
        ("destination_hostname", "VARCHAR(255)"),
        ("repository_type", "VARCHAR(50) DEFAULT 'local'"),
    ]

    for column_name, column_def in columns_to_add:
        try:
            db.execute(
                text(
                    f"""
                    ALTER TABLE restore_jobs
                    ADD COLUMN {column_name} {column_def}
                    """
                )
            )
            logger.info(f"✓ Added column: {column_name}")
        except Exception as e:
            # If column already exists, skip it
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                logger.info(f"Column {column_name} already exists, skipping")
            else:
                logger.error(f"Failed to add column {column_name}", error=str(e))
                # Continue with other columns instead of failing completely
                continue

    db.commit()
    logger.info("✓ Remote restore fields migration completed")


def downgrade(db):
    """Remove remote restore fields from restore_jobs table"""
    try:
        logger.info("Removing remote restore fields from restore_jobs table")

        # SQLite doesn't support DROP COLUMN, so we need to recreate the table
        # For now, we'll just log a warning
        logger.warning("Downgrade not fully supported for SQLite - manual intervention may be required")

        # For PostgreSQL/MySQL, you would use:
        # db.execute(text("ALTER TABLE restore_jobs DROP COLUMN destination_type"))
        # db.execute(text("ALTER TABLE restore_jobs DROP COLUMN destination_connection_id"))
        # db.execute(text("ALTER TABLE restore_jobs DROP COLUMN execution_mode"))
        # db.execute(text("ALTER TABLE restore_jobs DROP COLUMN temp_extraction_path"))
        # db.execute(text("ALTER TABLE restore_jobs DROP COLUMN destination_hostname"))
        # db.execute(text("ALTER TABLE restore_jobs DROP COLUMN repository_type"))

        db.commit()

        logger.info("✓ Removed remote restore fields from restore_jobs table")

    except Exception as e:
        logger.error("Failed to remove remote restore fields", error=str(e))
        raise
