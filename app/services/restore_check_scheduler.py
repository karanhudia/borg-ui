import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.maintenance_jobs import start_background_maintenance_job
from app.database.database import SessionLocal
from app.database.models import Repository, RestoreCheckJob
from app.services.restore_check_service import restore_check_service
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()


async def run_due_scheduled_restore_checks(
    db: Session, now: Optional[datetime] = None
) -> None:
    """Dispatch due scheduled restore verification jobs."""
    now = to_utc_naive(now or datetime.now(timezone.utc))
    repos = (
        db.query(Repository)
        .filter(
            Repository.restore_check_cron_expression.isnot(None),
            Repository.restore_check_cron_expression != "",
            or_(
                Repository.next_scheduled_restore_check.is_(None),
                Repository.next_scheduled_restore_check <= now,
            ),
        )
        .order_by(
            Repository.next_scheduled_restore_check.asc(),
            Repository.id.asc(),
        )
        .all()
    )

    for repo in repos:
        try:
            start_background_maintenance_job(
                db,
                repo,
                RestoreCheckJob,
                error_key="backend.errors.repo.restoreCheckAlreadyRunning",
                dispatcher=lambda job,
                repo_id=repo.id: restore_check_service.execute_restore_check(
                    job.id, repo_id
                ),
                extra_fields={
                    "probe_paths": repo.restore_check_paths,
                    "full_archive": bool(repo.restore_check_full_archive),
                    "scheduled_restore_check": True,
                },
            )
            repo.last_scheduled_restore_check = now
            try:
                repo.next_scheduled_restore_check = calculate_next_cron_run(
                    repo.restore_check_cron_expression,
                    now,
                    repo.restore_check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
                )
            except Exception as exc:
                logger.error(
                    "Failed to calculate next restore check time",
                    repo_id=repo.id,
                    cron_expression=repo.restore_check_cron_expression,
                    restore_check_timezone=repo.restore_check_timezone,
                    error=str(exc),
                )
                repo.next_scheduled_restore_check = None
            db.commit()
        except Exception as exc:
            logger.error(
                "Failed to create scheduled restore check",
                repo_id=repo.id,
                error=str(exc),
            )
            continue


class RestoreCheckScheduler:
    """Scheduler for cron-based restore verification jobs."""

    def __init__(self):
        self.running = False

    async def run_scheduled_restore_checks(self):
        db = SessionLocal()
        try:
            await run_due_scheduled_restore_checks(db)
        finally:
            db.close()

    async def start(self):
        self.running = True
        while self.running:
            try:
                await self.run_scheduled_restore_checks()
            except Exception as exc:
                logger.error("Restore check scheduler error", error=str(exc))
            await asyncio.sleep(60)

    def stop(self):
        self.running = False


restore_check_scheduler = RestoreCheckScheduler()
