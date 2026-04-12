"""Add inline script parameter columns to repositories"""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def upgrade(db):
    """Add repository-level inline script parameter columns"""
    try:
        db.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN pre_backup_script_parameters JSON
        """))
        logger.info("Added repositories.pre_backup_script_parameters")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            logger.info("repositories.pre_backup_script_parameters already exists")
        else:
            raise

    try:
        db.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN post_backup_script_parameters JSON
        """))
        logger.info("Added repositories.post_backup_script_parameters")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            logger.info("repositories.post_backup_script_parameters already exists")
        else:
            raise

    db.commit()
    logger.info("Migration 087_add_repository_inline_script_parameters completed successfully")


def downgrade(db):
    logger.warning("Downgrade not supported for SQLite - repository inline script parameter columns will remain")
