"""
Migration: Add unique constraint to scheduled_job_repositories junction table

This migration:
1. Removes any duplicate repository entries within the same schedule
2. Adds a unique constraint to prevent future duplicates

Created: 2026-02-04
"""

import structlog
from sqlalchemy import text

logger = structlog.get_logger()

def upgrade(db):
    """Add unique constraint to scheduled_job_repositories table"""

    # First, clean up any existing duplicates
    logger.info("Checking for duplicate repository entries in schedules...")

    # Query to find duplicates
    result = db.execute(text("""
        SELECT scheduled_job_id, repository_id, COUNT(*) as count
        FROM scheduled_job_repositories
        GROUP BY scheduled_job_id, repository_id
        HAVING COUNT(*) > 1
    """))

    duplicates = result.fetchall()

    if duplicates:
        logger.warning(f"Found {len(duplicates)} duplicate schedule-repository combinations")

        for dup in duplicates:
            schedule_id, repo_id, count = dup
            logger.info(f"Removing duplicates for schedule_id={schedule_id}, repository_id={repo_id} (count={count})")

            # Keep only the first entry (lowest execution_order), delete the rest
            db.execute(text("""
                DELETE FROM scheduled_job_repositories
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM scheduled_job_repositories
                    WHERE scheduled_job_id = :schedule_id
                    AND repository_id = :repo_id
                    GROUP BY scheduled_job_id, repository_id
                )
                AND scheduled_job_id = :schedule_id
                AND repository_id = :repo_id
            """), {"schedule_id": schedule_id, "repo_id": repo_id})

        db.commit()
        logger.info("Duplicate cleanup completed")
    else:
        logger.info("No duplicate entries found")

    # Add unique constraint
    logger.info("Adding unique constraint to scheduled_job_repositories table...")

    try:
        db.execute(text("""
            CREATE UNIQUE INDEX uq_schedule_repository
            ON scheduled_job_repositories (scheduled_job_id, repository_id)
        """))
        db.commit()
        logger.info("Unique constraint added successfully")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            logger.info("Unique constraint already exists, skipping")
        else:
            raise


def downgrade(db):
    """Remove unique constraint from scheduled_job_repositories table"""

    logger.info("Removing unique constraint from scheduled_job_repositories table...")

    try:
        db.execute(text("DROP INDEX IF EXISTS uq_schedule_repository"))
        db.commit()
        logger.info("Unique constraint removed")
    except Exception as e:
        logger.error(f"Failed to remove unique constraint: {e}")
        raise
