from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import Repository, RepositoryStorage, RcloneSyncJob
from app.services.rclone_repository_service import rclone_repository_service
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()


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


def _record_scheduler_failure(
    db: Session,
    *,
    storage_id: int,
    repository_id: int,
    direction: str,
    scheduled_for: datetime,
    now: datetime,
    message: str,
) -> None:
    db.rollback()
    storage = (
        db.query(RepositoryStorage).filter(RepositoryStorage.id == storage_id).first()
    )
    if storage:
        storage.sync_status = "failed"
        storage.last_sync_error = message
        storage.last_scheduled_sync_at = now
        storage.next_scheduled_sync_at = _calculate_next_sync_run(storage, now)

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
                started_at=now,
                completed_at=now,
                error_text=message,
                log_text=message,
            )
        )
    db.commit()


async def run_due_scheduled_rclone_mirrors(
    db: Session, now: Optional[datetime] = None
) -> None:
    """Run due repository cloud mirror syncs through the shared scheduler loop."""
    now = to_utc_naive(now or datetime.now(timezone.utc))
    due_storages = (
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
        .all()
    )

    if not due_storages:
        logger.debug("No repositories due for scheduled rclone mirror syncs", time=now)
        return

    logger.info("Found due scheduled rclone mirror syncs", count=len(due_storages))
    for storage in due_storages:
        scheduled_for = storage.next_scheduled_sync_at or now
        storage_id = storage.id
        repository_id = storage.repository_id
        direction = storage.sync_direction
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
            storage.last_scheduled_sync_at = now
            storage.next_scheduled_sync_at = _calculate_next_sync_run(storage, now)
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
                now=now,
                message=message,
            )
