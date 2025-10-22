"""
Add size-based progress fields to backup_jobs table
"""

from sqlalchemy import Column, BigInteger, Integer
import structlog

logger = structlog.get_logger()

def upgrade(engine):
    """Add total_expected_size and estimated_time_remaining columns"""
    try:
        with engine.connect() as conn:
            # Add total_expected_size column
            conn.execute("""
                ALTER TABLE backup_jobs
                ADD COLUMN total_expected_size BIGINT DEFAULT 0
            """)

            # Add estimated_time_remaining column
            conn.execute("""
                ALTER TABLE backup_jobs
                ADD COLUMN estimated_time_remaining INTEGER DEFAULT 0
            """)

            conn.commit()

        logger.info("Added size-based progress fields to backup_jobs")
    except Exception as e:
        logger.error("Failed to add size-based progress fields", error=str(e))
        raise

def downgrade(engine):
    """Remove total_expected_size and estimated_time_remaining columns"""
    try:
        with engine.connect() as conn:
            conn.execute("""
                ALTER TABLE backup_jobs
                DROP COLUMN total_expected_size
            """)

            conn.execute("""
                ALTER TABLE backup_jobs
                DROP COLUMN estimated_time_remaining
            """)

            conn.commit()

        logger.info("Removed size-based progress fields from backup_jobs")
    except Exception as e:
        logger.error("Failed to remove size-based progress fields", error=str(e))
        raise
