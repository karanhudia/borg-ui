from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional

import structlog
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.maintenance_jobs import start_background_maintenance_job
from app.core.borg_router import BorgRouter
from app.database.models import CheckJob, Repository, SystemSettings
from app.utils.process_utils import is_process_alive
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()

STALE_PENDING_SCHEDULED_CHECK_AFTER = timedelta(minutes=15)


def _utc_naive(value: datetime) -> datetime:
    return to_utc_naive(value)


def _mark_stale_scheduled_check_failed(
    job: CheckJob, now: datetime, message: str
) -> None:
    job.status = "failed"
    job.completed_at = now
    job.error_message = message
    job.progress_message = message


def cleanup_stale_scheduled_check_jobs(db: Session, now: datetime) -> int:
    """Fail scheduled check jobs that can no longer be dispatched or monitored."""
    cutoff = now - STALE_PENDING_SCHEDULED_CHECK_AFTER
    stale_count = 0

    stale_pending_jobs = (
        db.query(CheckJob)
        .filter(
            CheckJob.scheduled_check == True,
            CheckJob.status == "pending",
            or_(CheckJob.created_at.is_(None), CheckJob.created_at <= cutoff),
        )
        .all()
    )
    for job in stale_pending_jobs:
        _mark_stale_scheduled_check_failed(
            job,
            now,
            "Scheduled check did not start before the dispatcher timeout",
        )
        stale_count += 1

    running_jobs = (
        db.query(CheckJob)
        .filter(CheckJob.scheduled_check == True, CheckJob.status == "running")
        .all()
    )
    for job in running_jobs:
        started_at = job.started_at or job.created_at
        if started_at and _utc_naive(started_at) > cutoff:
            continue
        if is_process_alive(job.process_pid, job.process_start_time):
            continue

        _mark_stale_scheduled_check_failed(
            job,
            now,
            "Scheduled check process is no longer running",
        )
        stale_count += 1

    if stale_count:
        db.commit()
        logger.warning("Cleaned up stale scheduled check jobs", count=stale_count)

    return stale_count


def count_active_scheduled_check_jobs(db: Session, now: datetime) -> int:
    pending_cutoff = now - STALE_PENDING_SCHEDULED_CHECK_AFTER
    return (
        db.query(CheckJob)
        .filter(
            CheckJob.scheduled_check == True,
            or_(
                CheckJob.status == "running",
                and_(
                    CheckJob.status == "pending",
                    CheckJob.created_at.isnot(None),
                    CheckJob.created_at > pending_cutoff,
                ),
            ),
        )
        .count()
    )


async def run_due_scheduled_checks(db: Session, now: Optional[datetime] = None) -> None:
    """
    Execute scheduled checks that are due.

    This helper is intentionally scheduler-loop agnostic so check schedules can
    run through the same minute-based scheduling engine as backup schedules.
    """
    now = _utc_naive(now or datetime.utcnow())
    settings = db.query(SystemSettings).first()
    max_scheduled_checks = (
        settings.max_concurrent_scheduled_checks
        if settings and settings.max_concurrent_scheduled_checks is not None
        else 4
    )

    if max_scheduled_checks <= 0:
        logger.info("Scheduled check dispatch disabled", limit=max_scheduled_checks)
        return

    cleanup_stale_scheduled_check_jobs(db, now)
    active_scheduled_checks = count_active_scheduled_check_jobs(db, now)
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
            Repository.check_schedule_enabled.is_(True),
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
                    "extra_flags": repo.check_extra_flags,
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
                repo.next_scheduled_check = calculate_next_cron_run(
                    repo.check_cron_expression,
                    now,
                    repo.check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
                )
            except Exception as exc:
                logger.error(
                    "Failed to calculate next check time",
                    repo_id=repo.id,
                    cron_expression=repo.check_cron_expression,
                    check_timezone=repo.check_timezone,
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
                check_timezone=repo.check_timezone,
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
