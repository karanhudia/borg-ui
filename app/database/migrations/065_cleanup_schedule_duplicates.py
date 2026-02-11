"""
Migration: Fix schedule junction table issues

This migration:
1. Cleans up orphaned junction entries (pointing to deleted schedules)
2. Removes duplicate entries (same schedule + same repo)
3. Recreates table with proper CASCADE delete behavior

Background:
- Foreign keys were disabled when tables were created
- ondelete="CASCADE" in model didn't take effect
- Manual fix required for existing databases

Created: 2026-02-11
"""

import structlog
from sqlalchemy import text

logger = structlog.get_logger()

def upgrade(db):
    """Clean up duplicates/orphans and add CASCADE delete to scheduled_job_repositories"""

    try:
        # STEP 1: Clean up orphaned junction entries (pointing to deleted schedules)
        logger.info("STEP 1: Checking for orphaned junction entries...")
        result = db.execute(text("""
            SELECT sjr.id, sjr.scheduled_job_id, sjr.repository_id
            FROM scheduled_job_repositories sjr
            LEFT JOIN scheduled_jobs sj ON sjr.scheduled_job_id = sj.id
            WHERE sj.id IS NULL
        """))

        orphans = result.fetchall()

        if orphans:
            logger.warning(f"Found {len(orphans)} orphaned junction entries, cleaning up...")
            for orphan in orphans:
                entry_id, schedule_id, repo_id = orphan
                logger.debug(f"Deleting orphaned entry: id={entry_id}, schedule_id={schedule_id} (deleted), repo_id={repo_id}")
                db.execute(text("DELETE FROM scheduled_job_repositories WHERE id = :id"), {"id": entry_id})

            db.commit()
            logger.info(f"STEP 1: Removed {len(orphans)} orphaned junction entries")
        else:
            logger.info("STEP 1: No orphaned junction entries found")

        # STEP 2: Remove duplicate entries
        logger.info("STEP 2: Checking for duplicate entries...")
        result = db.execute(text("""
            SELECT scheduled_job_id, repository_id, COUNT(*) as count
            FROM scheduled_job_repositories
            GROUP BY scheduled_job_id, repository_id
            HAVING COUNT(*) > 1
        """))

        duplicates = result.fetchall()

        if duplicates:
            logger.warning(f"Found {len(duplicates)} duplicate schedule-repository combinations, cleaning up...")

            total_removed = 0
            for dup in duplicates:
                schedule_id, repo_id, count = dup
                logger.info(f"Cleaning: schedule_id={schedule_id}, repo_id={repo_id}, duplicates={count}")

                # Get all entries for this combination, ordered by id (keep oldest)
                entries_result = db.execute(text("""
                    SELECT id, execution_order
                    FROM scheduled_job_repositories
                    WHERE scheduled_job_id = :schedule_id
                    AND repository_id = :repo_id
                    ORDER BY id ASC
                """), {"schedule_id": schedule_id, "repo_id": repo_id})

                entries = entries_result.fetchall()

                if len(entries) > 1:
                    # Keep the first entry, delete the rest
                    keep_id = entries[0][0]
                    delete_ids = [entry[0] for entry in entries[1:]]

                    logger.debug(f"  Keeping entry id={keep_id}, deleting ids={delete_ids}")

                    for delete_id in delete_ids:
                        db.execute(text("DELETE FROM scheduled_job_repositories WHERE id = :id"), {"id": delete_id})
                        total_removed += 1

            db.commit()
            logger.info(f"STEP 2: Removed {total_removed} duplicate entries")
        else:
            logger.info("STEP 2: No duplicate entries found")

        # STEP 3: Recreate table with CASCADE delete
        logger.info("STEP 3: Adding CASCADE delete to scheduled_job_repositories table...")

        # Create new table with CASCADE
        db.execute(text("""
            CREATE TABLE scheduled_job_repositories_new (
                id INTEGER PRIMARY KEY,
                scheduled_job_id INTEGER NOT NULL,
                repository_id INTEGER NOT NULL,
                execution_order INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scheduled_job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
                FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE,
                UNIQUE (scheduled_job_id, repository_id)
            )
        """))

        # Copy data from old table to new table
        db.execute(text("""
            INSERT INTO scheduled_job_repositories_new
                (id, scheduled_job_id, repository_id, execution_order, created_at)
            SELECT id, scheduled_job_id, repository_id, execution_order, created_at
            FROM scheduled_job_repositories
        """))

        # Drop old table
        db.execute(text("DROP TABLE scheduled_job_repositories"))

        # Rename new table to old name
        db.execute(text("""
            ALTER TABLE scheduled_job_repositories_new
            RENAME TO scheduled_job_repositories
        """))

        # Recreate indexes
        db.execute(text("""
            CREATE INDEX ix_scheduled_job_repositories_scheduled_job_id
            ON scheduled_job_repositories(scheduled_job_id)
        """))

        db.execute(text("""
            CREATE INDEX ix_scheduled_job_repositories_repository_id
            ON scheduled_job_repositories(repository_id)
        """))

        db.commit()
        logger.info("STEP 3: CASCADE delete added successfully to scheduled_job_repositories")

        logger.info("✓ Migration 065 completed successfully")

    except Exception as e:
        logger.error(f"Migration 065 failed: {e}")
        db.rollback()
        # Don't raise - we don't want to block startup
        # The atomic transaction fix + manual cleanup will work as fallback


def downgrade(db):
    """Recreate table without CASCADE (reverse migration)"""

    try:
        logger.info("Removing CASCADE delete from scheduled_job_repositories...")

        # Create table without CASCADE
        db.execute(text("""
            CREATE TABLE scheduled_job_repositories_old (
                id INTEGER PRIMARY KEY,
                scheduled_job_id INTEGER NOT NULL,
                repository_id INTEGER NOT NULL,
                execution_order INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scheduled_job_id) REFERENCES scheduled_jobs(id),
                FOREIGN KEY (repository_id) REFERENCES repositories(id),
                UNIQUE (scheduled_job_id, repository_id)
            )
        """))

        # Copy data
        db.execute(text("""
            INSERT INTO scheduled_job_repositories_old
                (id, scheduled_job_id, repository_id, execution_order, created_at)
            SELECT id, scheduled_job_id, repository_id, execution_order, created_at
            FROM scheduled_job_repositories
        """))

        # Drop and rename
        db.execute(text("DROP TABLE scheduled_job_repositories"))
        db.execute(text("""
            ALTER TABLE scheduled_job_repositories_old
            RENAME TO scheduled_job_repositories
        """))

        # Recreate indexes
        db.execute(text("""
            CREATE INDEX ix_scheduled_job_repositories_scheduled_job_id
            ON scheduled_job_repositories(scheduled_job_id)
        """))

        db.execute(text("""
            CREATE INDEX ix_scheduled_job_repositories_repository_id
            ON scheduled_job_repositories(repository_id)
        """))

        db.commit()
        logger.info("CASCADE delete removed")

    except Exception as e:
        logger.error(f"Failed to remove CASCADE delete: {e}")
        db.rollback()
        raise
