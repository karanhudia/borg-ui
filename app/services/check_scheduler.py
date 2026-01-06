import asyncio
from datetime import datetime
import structlog
from sqlalchemy.orm import Session
from sqlalchemy import or_
from croniter import croniter
from app.database.models import Repository, CheckJob
from app.database.database import SessionLocal
from app.services.check_service import check_service

logger = structlog.get_logger()


class CheckScheduler:
    """Scheduler for cron-based repository checks"""

    def __init__(self):
        self.running = False

    async def run_scheduled_checks(self):
        """
        Check for repositories that need scheduled checks and execute them.
        Called periodically (every hour) by the background task.
        """
        db = SessionLocal()
        try:
            now = datetime.utcnow()

            # Find repositories that:
            # 1. Have check_cron_expression set (not NULL and not empty)
            # 2. Either never checked (next_scheduled_check is NULL) or due for check (next_scheduled_check <= now)
            repos = db.query(Repository).filter(
                Repository.check_cron_expression.isnot(None),
                Repository.check_cron_expression != "",
                or_(
                    Repository.next_scheduled_check.is_(None),
                    Repository.next_scheduled_check <= now
                )
            ).all()

            if not repos:
                logger.debug("No repositories due for scheduled checks", time=now)
                return

            logger.info("Found repositories due for scheduled checks",
                       count=len(repos),
                       repositories=[r.name for r in repos])

            for repo in repos:
                try:
                    # Create check job
                    check_job = CheckJob(
                        repository_id=repo.id,
                        status="pending",
                        max_duration=repo.check_max_duration or 3600,  # Default to 1 hour if not set
                        scheduled_check=True  # Mark as scheduled check
                    )
                    db.add(check_job)
                    db.flush()  # Get the job ID

                    logger.info("Created scheduled check job",
                               repo_id=repo.id,
                               repo_name=repo.name,
                               check_job_id=check_job.id,
                               max_duration=check_job.max_duration)

                    # Update schedule timestamps BEFORE executing (in case execution fails)
                    repo.last_scheduled_check = now

                    # Calculate next check time from cron expression
                    try:
                        cron = croniter(repo.check_cron_expression, now)
                        repo.next_scheduled_check = cron.get_next(datetime)
                    except Exception as e:
                        logger.error("Failed to calculate next check time",
                                   repo_id=repo.id,
                                   cron_expression=repo.check_cron_expression,
                                   error=str(e))
                        repo.next_scheduled_check = None

                    db.commit()

                    logger.info("Updated check schedule",
                               repo_id=repo.id,
                               repo_name=repo.name,
                               next_check=repo.next_scheduled_check,
                               cron_expression=repo.check_cron_expression)

                    # Execute check asynchronously (don't await - fire and forget)
                    asyncio.create_task(
                        check_service.execute_check(
                            job_id=check_job.id,
                            repository_id=repo.id
                        )
                    )

                    logger.info("Scheduled check started",
                               repo_id=repo.id,
                               repo_name=repo.name,
                               check_job_id=check_job.id,
                               next_check=repo.next_scheduled_check)

                except Exception as e:
                    logger.error("Failed to create scheduled check",
                                repo_id=repo.id,
                                repo_name=repo.name if repo else "Unknown",
                                error=str(e))
                    # Continue with other repositories even if one fails
                    continue

        except Exception as e:
            logger.error("Error in run_scheduled_checks", error=str(e))
        finally:
            db.close()

    async def start(self):
        """
        Start the scheduler background loop.
        Runs every hour to check for repositories that need checking.
        """
        self.running = True
        logger.info("Check scheduler started", check_interval_hours=1)

        while self.running:
            try:
                await self.run_scheduled_checks()
            except Exception as e:
                logger.error("Check scheduler error", error=str(e))

            # Wait 1 hour before next check
            # Using 3600 seconds (1 hour) to balance between responsiveness and efficiency
            await asyncio.sleep(3600)

        logger.info("Check scheduler stopped")

    def stop(self):
        """Stop the scheduler loop"""
        self.running = False
        logger.info("Check scheduler stop requested")


# Global instance
check_scheduler = CheckScheduler()
