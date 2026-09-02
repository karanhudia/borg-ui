"""User-facing notifications for agent-executed jobs.

Server-side execution paths send their notifications from inside the backup
and check services. Agent-executed jobs never pass through those services -
they reach their terminal state in the agent transport handlers (WebSocket +
REST) and in the agent job reaper - so without an explicit dispatch there,
configured notifications (backup start/success/warning/failure, check
success/failure) silently never fire for agent repositories.

This module renders the linked job rows into the same notification calls the
server-side paths make. Callers invoke it after the terminal state has been
committed; the entire dispatch - including every ORM attribute read, which can
itself hit the database on a committed (expired) object - runs inside the
exception boundary, so a failure is logged and never propagates into the
agent protocol.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.database.models import (
    AgentJob,
    BackupJob,
    BackupPlan,
    CheckJob,
    Repository,
    ScheduledJob,
)
from app.services.notification_service import notification_service

logger = structlog.get_logger()


def orm_identity_id(obj: Any) -> Optional[int]:
    """Primary key from the ORM identity map - no database access, so it is
    safe to call on an expired object inside an exception handler."""
    identity = sa_inspect(obj).identity
    return identity[0] if identity else None


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def backup_job_label(db: Session, backup_job: BackupJob) -> Optional[str]:
    """Plan or schedule name for notification titles, if any."""
    if backup_job.backup_plan_id:
        plan = (
            db.query(BackupPlan)
            .filter(BackupPlan.id == backup_job.backup_plan_id)
            .first()
        )
        if plan and plan.name:
            return plan.name
    if backup_job.scheduled_job_id:
        scheduled_job = (
            db.query(ScheduledJob)
            .filter(ScheduledJob.id == backup_job.scheduled_job_id)
            .first()
        )
        if scheduled_job and scheduled_job.name:
            return scheduled_job.name
    return None


async def notify_backup_job_started(
    db: Session, agent_job: AgentJob, backup_job: BackupJob
) -> None:
    """Send the backup-start notification for an agent backup job."""
    try:
        payload = agent_job.payload or {}
        backup_payload = payload.get("backup") if isinstance(payload, dict) else None
        source_paths = None
        if isinstance(backup_payload, dict):
            raw_paths = backup_payload.get("source_paths")
            if isinstance(raw_paths, list):
                source_paths = [str(path) for path in raw_paths]

        await notification_service.send_backup_start(
            db,
            backup_job.repository,
            backup_job.archive_name or "",
            source_paths,
            None,
            backup_job_label(db, backup_job),
        )
    except Exception as exc:
        logger.warning(
            "Failed to send agent backup start notification",
            backup_job_id=orm_identity_id(backup_job),
            error=str(exc),
        )


async def notify_backup_job_finished(db: Session, backup_job: BackupJob) -> None:
    """Send the success/warning/failure notification for a finished backup job.

    Statuses without a server-side notification (e.g. cancelled) are skipped.
    """
    status_value = None
    try:
        status_value = backup_job.status
        if status_value not in ("completed", "completed_with_warnings", "failed"):
            return

        job_name = backup_job_label(db, backup_job)
        if status_value == "failed":
            await notification_service.send_backup_failure(
                db,
                backup_job.repository,
                backup_job.error_message or "Unknown error",
                backup_job.id,
                job_name,
            )
            return

        stats = {
            "original_size": backup_job.original_size,
            "compressed_size": backup_job.compressed_size,
            "deduplicated_size": backup_job.deduplicated_size,
        }
        if status_value == "completed_with_warnings":
            await notification_service.send_backup_warning(
                db,
                backup_job.repository,
                backup_job.archive_name or "",
                backup_job.error_message or "",
                stats,
                _as_utc(backup_job.completed_at),
                job_name,
                started_at=_as_utc(backup_job.started_at),
                nfiles=backup_job.nfiles,
            )
        else:
            await notification_service.send_backup_success(
                db,
                backup_job.repository,
                backup_job.archive_name or "",
                stats,
                _as_utc(backup_job.completed_at),
                job_name,
                started_at=_as_utc(backup_job.started_at),
                nfiles=backup_job.nfiles,
            )
    except Exception as exc:
        logger.warning(
            "Failed to send agent backup notification",
            backup_job_id=orm_identity_id(backup_job),
            status=status_value,
            error=str(exc),
        )


async def notify_check_job_finished(db: Session, check_job: CheckJob) -> None:
    """Send the check success/failure notification for a finished check job.

    A check that completed with warnings still verified the repository and is
    reported as completed, matching how the server-side path classifies it.
    """
    status_value = None
    try:
        status_value = check_job.status
        if status_value not in ("completed", "completed_with_warnings", "failed"):
            return

        repository = (
            db.query(Repository)
            .filter(Repository.id == check_job.repository_id)
            .first()
        )
        duration_seconds = None
        started_at = _as_utc(check_job.started_at)
        completed_at = _as_utc(check_job.completed_at)
        if started_at and completed_at:
            duration_seconds = int((completed_at - started_at).total_seconds())

        notified_status = "failed" if status_value == "failed" else "completed"
        await notification_service.send_check_completion(
            db=db,
            repository_name=repository.name if repository else "Unknown",
            repository_path=repository.path if repository else "Unknown",
            status=notified_status,
            duration_seconds=duration_seconds,
            error_message=check_job.error_message
            if notified_status == "failed"
            else None,
            check_type="scheduled" if check_job.scheduled_check else "manual",
        )
    except Exception as exc:
        logger.warning(
            "Failed to send agent check notification",
            check_job_id=orm_identity_id(check_job),
            status=status_value,
            error=str(exc),
        )
