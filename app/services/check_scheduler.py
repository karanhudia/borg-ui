from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import Operation, Repository, SystemSettings
from app.services.operations.maintenance_start import start_maintenance
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()


def _utc_naive(value: datetime) -> datetime:
    return to_utc_naive(value)


def count_active_scheduled_operations(db: Session) -> int:
    """Scheduled checks waiting or running in `operations` (spec 6.2 keeps
    the flag in `params`, so the filter happens in Python; the row count is
    tiny)."""
    rows = (
        db.query(Operation)
        .filter(
            Operation.kind == "check",
            Operation.status.in_(("queued", "running")),
        )
        .all()
    )
    return sum(1 for row in rows if (row.params or {}).get("scheduled_check"))


def count_active_scheduled_check_jobs(db: Session, now: datetime) -> int:
    """`now` is unused since the scheduled checks became operations, and is
    kept because the dispatcher and its tests pass it."""
    return count_active_scheduled_operations(db)


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
            check_job = start_maintenance(
                db,
                repo,
                "check",
                trigger="schedule",
                params={
                    "max_duration": (
                        repo.check_max_duration
                        if repo.check_max_duration is not None
                        else 3600
                    ),
                    "extra_flags": repo.check_extra_flags,
                    "scheduled_check": True,
                },
                user_id=None,
                duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
            )

            logger.info(
                "Created scheduled check job",
                repo_id=repo.id,
                repo_name=repo.name,
                check_job_id=check_job.id,
                max_duration=(check_job.params or {}).get("max_duration"),
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
