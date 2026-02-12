"""
Migration 066: Add ssh_path_prefix field to ssh_connections table

This field allows specifying a path prefix that gets prepended to repository paths
when executing SSH commands (e.g., borg init, borg create), but NOT when browsing
via SFTP.

Use case: Synology NAS
- SFTP path: /share11/testtest
- Actual SSH path: /volume1/share11/testtest
- ssh_path_prefix: /volume1

When browsing with SFTP, the path is used as-is.
When executing borg commands over SSH, the prefix is prepended.

Related to GitHub issue #230
"""

import structlog
from sqlalchemy import text

logger = structlog.get_logger()


def upgrade(db):
    """Add ssh_path_prefix column to ssh_connections table"""
    try:
        logger.info("Adding ssh_path_prefix column to ssh_connections table")

        # Add the new column (nullable)
        db.execute(
            text(
                """
                ALTER TABLE ssh_connections
                ADD COLUMN ssh_path_prefix TEXT
                """
            )
        )
        db.commit()

        logger.info("✓ Added ssh_path_prefix column to ssh_connections table")

    except Exception as e:
        # If column already exists (migration already ran), that's okay
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            logger.info("ssh_path_prefix column already exists, skipping")
        else:
            logger.error("Failed to add ssh_path_prefix column", error=str(e))
            raise
