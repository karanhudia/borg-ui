from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import Repository, RepositoryStorage, RcloneSyncJob
from app.services.rclone_repository_service import rclone_repository_service
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()
_active_scheduled_mirror_tasks: set[int] = set()


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
    return (
        db.query(RcloneSyncJob)
        .filter(
            RcloneSyncJob.repository_id == repository_id,
            RcloneSyncJob.triggered_by == "schedule",
            RcloneSyncJob.scheduled_for == scheduled_for,
        )
        .first()
        is not None
    )


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


def _track_scheduled_mirror_task(task: asyncio.Task, storage_id: int) -> None:
    _active_scheduled_mirror_tasks.add(storage_id)

    def _cleanup(_task: asyncio.Task) -> None:
        _active_scheduled_mirror_tasks.discard(storage_id)

    task.add_done_callback(_cleanup)


def _record_scheduler_failure(
    db: Session,
    *,
    storage_id: int,
    repository_id: int,
    direction: str,
    scheduled_for: datetime,
    finished_at: datetime,
    message: str,
) -> None:
    db.rollback()
    storage = (
        db.query(RepositoryStorage).filter(RepositoryStorage.id == storage_id).first()
    )
    if storage:
        storage.sync_status = "failed"
        storage.last_sync_error = message
        storage.last_scheduled_sync_at = finished_at
        storage.next_scheduled_sync_at = _calculate_next_sync_run(storage, finished_at)

    if not _scheduled_job_exists(
        db,
        repository_id=repository_id,
        scheduled_for=scheduled_for,
    ):
        db.add(
            RcloneSyncJob(
                repository_id=repository_id,
                direction=direction,
                status="failed",
                triggered_by="schedule",
                scheduled_for=scheduled_for,
                started_at=finished_at,
                completed_at=finished_at,
                error_text=message,
                log_text=message,
            )
        )
    db.commit()


async def _run_scheduled_rclone_mirror_task(
    *,
    storage_id: int,
    repository_id: int,
    scheduled_for: datetime,
    direction: str,
) -> None:
    db = SessionLocal()
    try:
        storage = (
            db.query(RepositoryStorage)
            .filter(RepositoryStorage.id == storage_id)
            .first()
        )
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if storage is None or repository is None:
            logger.warning(
                "Skipping scheduled rclone mirror sync for missing storage or repository",
                repository_id=repository_id,
                storage_id=storage_id,
            )
            return

        try:
            await rclone_repository_service.sync_repository(
                db,
                repository,
                triggered_by="schedule",
                scheduled_for=scheduled_for,
            )
            db.refresh(storage)
            finished_at = _scheduler_time()
            storage.last_scheduled_sync_at = finished_at
            storage.next_scheduled_sync_at = _calculate_next_sync_run(
                storage, finished_at
            )
            db.commit()
            logger.info(
                "Scheduled rclone mirror sync completed",
                repository_id=repository_id,
                status=storage.sync_status,
                next_scheduled_sync_at=storage.next_scheduled_sync_at,
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            logger.error(
                "Scheduled rclone mirror sync failed",
                repository_id=repository_id,
                error=message,
            )
            _record_scheduler_failure(
                db,
                storage_id=storage_id,
                repository_id=repository_id,
                direction=direction,
                scheduled_for=scheduled_for,
                finished_at=_scheduler_time(),
                message=message,
            )
    finally:
        db.close()


def dispatch_due_scheduled_rclone_mirrors(
    db: Session, now: Optional[datetime] = None
) -> int:
    """Claim and dispatch due repository cloud mirror syncs in background tasks."""
    now = _scheduler_time(now)
    due_storages = _due_scheduled_storage_query(db, now).all()

    if not due_storages:
        logger.debug("No repositories due for scheduled rclone mirror syncs", time=now)
        return 0

    dispatched = 0
    for storage in due_storages:
        if storage.id in _active_scheduled_mirror_tasks:
            continue
        scheduled_for = storage.next_scheduled_sync_at or now
        storage.next_scheduled_sync_at = _calculate_next_sync_run(storage, now)
        db.commit()

        task = asyncio.create_task(
            _run_scheduled_rclone_mirror_task(
                storage_id=storage.id,
                repository_id=storage.repository_id,
                scheduled_for=scheduled_for,
                direction=storage.sync_direction,
            )
        )
        _track_scheduled_mirror_task(task, storage.id)
        dispatched += 1

    if dispatched:
        logger.info("Dispatched scheduled rclone mirror syncs", count=dispatched)
    return dispatched


async def run_due_scheduled_rclone_mirrors(
    db: Session, now: Optional[datetime] = None
) -> None:
    """Run due repository cloud mirror syncs through the shared scheduler loop."""
    injected_now = now
    now = _scheduler_time(now)
    due_storages = _due_scheduled_storage_query(db, now).all()

    if not due_storages:
        logger.debug("No repositories due for scheduled rclone mirror syncs", time=now)
        return

    logger.info("Found due scheduled rclone mirror syncs", count=len(due_storages))
    for storage in due_storages:
        scheduled_for = storage.next_scheduled_sync_at or now
        storage_id = storage.id
        repository_id = storage.repository_id
        direction = storage.sync_direction
        storage.next_scheduled_sync_at = _calculate_next_sync_run(storage, now)
        db.commit()
        repository = (
            db.query(Repository).filter(Repository.id == storage.repository_id).first()
        )
        if repository is None:
            logger.warning(
                "Skipping scheduled rclone mirror sync for missing repository",
                repository_id=repository_id,
            )
            continue

        try:
            await rclone_repository_service.sync_repository(
                db,
                repository,
                triggered_by="schedule",
                scheduled_for=scheduled_for,
            )
            db.refresh(storage)
            finished_at = (
                _scheduler_time(injected_now) if injected_now else _scheduler_time()
            )
            storage.last_scheduled_sync_at = finished_at
            storage.next_scheduled_sync_at = _calculate_next_sync_run(
                storage, finished_at
            )
            db.commit()
            logger.info(
                "Scheduled rclone mirror sync completed",
                repository_id=repository_id,
                status=storage.sync_status,
                next_scheduled_sync_at=storage.next_scheduled_sync_at,
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            logger.error(
                "Scheduled rclone mirror sync failed",
                repository_id=repository_id,
                error=message,
            )
            _record_scheduler_failure(
                db,
                storage_id=storage_id,
                repository_id=repository_id,
                direction=direction,
                scheduled_for=scheduled_for,
                finished_at=(
                    _scheduler_time(injected_now) if injected_now else _scheduler_time()
                ),
                message=message,
            )
