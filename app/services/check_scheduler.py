from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import structlog
from croniter import croniter
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.maintenance_jobs import start_background_maintenance_job
from app.core.borg_router import BorgRouter
from app.database.models import CheckJob, Repository, SystemSettings

logger = structlog.get_logger()


async def run_due_scheduled_checks(db: Session, now: Optional[datetime] = None) -> None:
    """
    Execute scheduled checks that are due.

    This helper is intentionally scheduler-loop agnostic so check schedules can
    run through the same minute-based scheduling engine as backup schedules.
    """
    now = now or datetime.utcnow()
    settings = db.query(SystemSettings).first()
    max_scheduled_checks = (
        settings.max_concurrent_scheduled_checks
        if settings and settings.max_concurrent_scheduled_checks is not None
        else 4
    )

    if max_scheduled_checks <= 0:
        logger.info("Scheduled check dispatch disabled", limit=max_scheduled_checks)
        return

    active_scheduled_checks = (
        db.query(CheckJob)
        .filter(
            CheckJob.scheduled_check == True,
            CheckJob.status.in_(["pending", "running"]),
        )
        .count()
    )
    available_slots = max_scheduled_checks - active_scheduled_checks
    if available_slots <= 0:
        logger.info(
            "Scheduled check capacity reached",
            limit=max_scheduled_checks,
            active=active_scheduled_checks,
        )
        return

    repos = (
        db.query(Repository)
        .filter(
            Repository.check_cron_expression.isnot(None),
            Repository.check_cron_expression != "",
            or_(
                Repository.next_scheduled_check.is_(None),
                Repository.next_scheduled_check <= now,
            ),
        )
        .order_by(Repository.next_scheduled_check.asc(), Repository.id.asc())
        .all()
    )

    if not repos:
        logger.debug("No repositories due for scheduled checks", time=now)
        return

    logger.info(
        "Found repositories due for scheduled checks",
        count=len(repos),
        repositories=[repo.name for repo in repos],
    )

    dispatched = 0
    for repo in repos:
        if dispatched >= available_slots:
            break
        try:
            check_job = start_background_maintenance_job(
                db,
                repo,
                CheckJob,
                error_key="backend.errors.repo.checkAlreadyRunning",
                dispatcher=lambda job,
                router_repo=SimpleNamespace(
                    id=repo.id,
                    borg_version=repo.borg_version,
                ): BorgRouter(router_repo).check(job.id),
                extra_fields={
                    "max_duration": repo.check_max_duration or 3600,
                    "scheduled_check": True,
                },
            )

            logger.info(
                "Created scheduled check job",
                repo_id=repo.id,
                repo_name=repo.name,
                check_job_id=check_job.id,
                max_duration=check_job.max_duration,
            )

            repo.last_scheduled_check = now

            try:
                cron = croniter(repo.check_cron_expression, now)
                repo.next_scheduled_check = cron.get_next(datetime)
            except Exception as exc:
                logger.error(
                    "Failed to calculate next check time",
                    repo_id=repo.id,
                    cron_expression=repo.check_cron_expression,
                    error=str(exc),
                )
                repo.next_scheduled_check = None

            db.commit()

            logger.info(
                "Updated check schedule",
                repo_id=repo.id,
                repo_name=repo.name,
                next_check=repo.next_scheduled_check,
                cron_expression=repo.check_cron_expression,
            )

            logger.info(
                "Scheduled check started",
                repo_id=repo.id,
                repo_name=repo.name,
                check_job_id=check_job.id,
                next_check=repo.next_scheduled_check,
            )
            dispatched += 1

        except Exception as exc:
            logger.error(
                "Failed to create scheduled check",
                repo_id=repo.id,
                repo_name=repo.name if repo else "Unknown",
                error=str(exc),
            )
            continue

    deferred = len(repos) - dispatched
    if deferred > 0:
        logger.info(
            "Deferred due scheduled checks until capacity is available",
            deferred=deferred,
            dispatched=dispatched,
            limit=max_scheduled_checks,
        )
