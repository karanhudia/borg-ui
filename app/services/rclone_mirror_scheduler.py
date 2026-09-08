from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import (
    Operation,
    OperationRcloneDetails,
    RcloneSyncJob,
    Repository,
    RepositoryStorage,
)
from app.services.operations.enqueue import enqueue, wake_runner
from app.services.operations.rclone_facade import RcloneSyncFacade
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()


def _scheduler_time(now: Optional[datetime] = None) -> datetime:
    return to_utc_naive(now or datetime.now(timezone.utc))


def _calculate_next_sync_run(
    storage: RepositoryStorage, now: datetime
) -> datetime | None:
    if not storage.sync_cron_expression:
        return None
    try:
        return calculate_next_cron_run(
            storage.sync_cron_expression,
            now,
            storage.sync_timezone or DEFAULT_SCHEDULE_TIMEZONE,
        )
    except Exception as exc:
        logger.error(
            "Failed to calculate next scheduled rclone mirror sync",
            repository_id=storage.repository_id,
            cron_expression=storage.sync_cron_expression,
            sync_timezone=storage.sync_timezone,
            error=str(exc),
        )
        return None


def _scheduled_job_exists(
    db: Session,
    *,
    repository_id: int,
    scheduled_for: datetime,
) -> bool:
    """True when this repository already has a mirror run for this slot, so a
    second scheduler tick does not enqueue a duplicate."""
    exists = (
        db.query(Operation.id)
        .join(
            OperationRcloneDetails,
            OperationRcloneDetails.operation_id == Operation.id,
        )
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "rclone_sync",
            Operation.trigger == "schedule",
            OperationRcloneDetails.scheduled_for == scheduled_for,
        )
        .first()
    )
    if exists is not None:
        return True
    # Pre-phase-6 rows only; goes away with the table in phase 9.
    return (
        db.query(RcloneSyncJob.id)
        .filter(
            RcloneSyncJob.repository_id == repository_id,
            RcloneSyncJob.triggered_by == "schedule",
            RcloneSyncJob.scheduled_for == scheduled_for,
        )
        .first()
        is not None
    )


def _enqueue_scheduled_mirror(
    db: Session, *, repository_id: int, direction: str, scheduled_for: datetime
) -> bool:
    """Queue one scheduled mirror sync. The runner dispatches it (spec 7.1),
    which is also what serialises it against the rclone lock scope (spec 7.2);
    this scheduler no longer runs syncs itself."""
    if _scheduled_job_exists(
        db, repository_id=repository_id, scheduled_for=scheduled_for
    ):
        return False
    operation = enqueue(
        db,
        "rclone_sync",
        repository_id=repository_id,
        trigger="schedule",
        commit=False,
    )
    job = RcloneSyncFacade(db, operation)
    job.direction = direction
    job.operation = "sync"
    job.scheduled_for = scheduled_for
    db.commit()
    wake_runner()
    return True


def _due_scheduled_storage_query(db: Session, now: datetime):
    query = (
        db.query(RepositoryStorage)
        .filter(
            RepositoryStorage.backend == "rclone",
            RepositoryStorage.sync_policy == "scheduled",
            RepositoryStorage.sync_cron_expression.isnot(None),
            RepositoryStorage.sync_cron_expression != "",
            or_(
                RepositoryStorage.next_scheduled_sync_at.is_(None),
                RepositoryStorage.next_scheduled_sync_at <= now,
            ),
        )
        .order_by(
            RepositoryStorage.next_scheduled_sync_at.asc(),
            RepositoryStorage.repository_id.asc(),
        )
    )
    dialect_name = getattr(db.get_bind().dialect, "name", "")
    if dialect_name == "postgresql":
        return query.with_for_update(skip_locked=True)
    return query


def dispatch_due_scheduled_rclone_mirrors(
    db: Session, now: Optional[datetime] = None
) -> int:
    """Queue due repository cloud mirror syncs. The runner starts them."""
    now = _scheduler_time(now)
    due_storages = _due_scheduled_storage_query(db, now).all()

    if not due_storages:
        logger.debug("No repositories due for scheduled rclone mirror syncs", time=now)
        return 0

    dispatched = 0
    for storage in due_storages:
        scheduled_for = storage.next_scheduled_sync_at or now
        storage.next_scheduled_sync_at = _calculate_next_sync_run(storage, now)
        db.commit()

        if _enqueue_scheduled_mirror(
            db,
            repository_id=storage.repository_id,
            direction=storage.sync_direction,
            scheduled_for=scheduled_for,
        ):
            dispatched += 1

    if dispatched:
        logger.info("Queued scheduled rclone mirror syncs", count=dispatched)
    return dispatched


async def run_due_scheduled_rclone_mirrors(
    db: Session, now: Optional[datetime] = None
) -> None:
    """Queue due repository cloud mirror syncs from the shared scheduler loop.

    Since phase 6 this only enqueues; the runner owns dispatch, the rclone lock
    scope, and failure recording. Kept async because the scheduler loop awaits
    it.
    """
    now = _scheduler_time(now)
    due_storages = _due_scheduled_storage_query(db, now).all()

    if not due_storages:
        logger.debug("No repositories due for scheduled rclone mirror syncs", time=now)
        return

    logger.info("Found due scheduled rclone mirror syncs", count=len(due_storages))
    for storage in due_storages:
        scheduled_for = storage.next_scheduled_sync_at or now
        repository_id = storage.repository_id
        direction = storage.sync_direction
        storage.next_scheduled_sync_at = _calculate_next_sync_run(storage, now)
        db.commit()
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if repository is None:
            logger.warning(
                "Skipping scheduled rclone mirror sync for missing repository",
                repository_id=repository_id,
            )
            continue

        if _enqueue_scheduled_mirror(
            db,
            repository_id=repository_id,
            direction=direction,
            scheduled_for=scheduled_for,
        ):
            logger.info(
                "Scheduled rclone mirror sync queued",
                repository_id=repository_id,
                next_scheduled_sync_at=storage.next_scheduled_sync_at,
            )
