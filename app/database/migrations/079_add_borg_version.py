"""Add borg_version to repositories and binary path settings to system_settings

Each repository now carries an integer borg_version (1 or 2) that controls
which binary and API path are used for all operations on that repo.

System settings gain two configurable binary paths so both borg 1 and borg 2
can coexist in the Docker image at different locations.
"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    # ── repositories.borg_version ─────────────────────────────────────────────
    try:
        db.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN borg_version INTEGER DEFAULT 1
        """))
        logger.info("Added borg_version column to repositories")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("borg_version column already exists on repositories")
        else:
            raise

    # ── system_settings.borg1_binary_path ────────────────────────────────────
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN borg1_binary_path VARCHAR DEFAULT 'borg'
        """))
        logger.info("Added borg1_binary_path column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("borg1_binary_path column already exists on system_settings")
        else:
            raise

    # ── system_settings.borg2_binary_path ────────────────────────────────────
    try:
        db.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN borg2_binary_path VARCHAR DEFAULT 'borg2'
        """))
        logger.info("Added borg2_binary_path column to system_settings")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("borg2_binary_path column already exists on system_settings")
        else:
            raise

    db.commit()
    logger.info("Migration 079_add_borg_version completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite — columns will remain")
