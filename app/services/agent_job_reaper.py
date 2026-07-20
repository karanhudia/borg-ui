"""Time-based reaper for orphaned in-flight agent jobs.

When an agent's session dies mid-job — e.g. a half-open WebSocket the server
never saw close, or an oversized `command_result` frame that broke the pipe —
the completion/failure never reaches the server and the AgentJob is stuck in an
active status forever. That permanently blocks the repository (the admission
control treats the stuck job as active work) and, for repository operations,
takes down concurrent jobs on the same session.

`_requeue_stale_agent_jobs` only runs on the agent's next hello, so a half-open
agent that never reconnects is never cleaned up. This reaper runs on a timer,
independent of reconnect, and marks such jobs terminally `failed` (not requeued,
so a repeatedly-failing job cannot flap between queued/running).

Healthy long-running jobs stream progress (borg `--progress` -> logs ->
`updated_at`), so their activity timestamp stays fresh and they are not reaped.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import AgentJob, BackupJob

logger = structlog.get_logger()

# In-flight statuses that indicate the agent is (or should be) working the job.
ACTIVE_IN_FLIGHT_STATUSES = ("claimed", "running", "cancel_requested")

# Backup-job statuses that must not be overwritten by the reaper.
TERMINAL_BACKUP_STATUSES = {
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
}

# A job with no activity for this long is treated as orphaned. Kept generous so
# a legitimately slow, silent operation is not killed; real operations that hang
# this long have lost their agent session.
AGENT_JOB_REAP_AFTER = timedelta(minutes=15)

# How often the background loop checks for orphaned jobs.
REAPER_INTERVAL_SECONDS = 60.0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _job_activity_at(job: AgentJob) -> datetime:
    """Most recent sign of life for the job (mirrors agents._job_activity_at)."""
    for value in (job.updated_at, job.started_at, job.claimed_at, job.created_at):
        if value is not None:
            return _as_utc(value)
    return datetime.now(timezone.utc)


def reap_stale_agent_jobs(
    db: Session,
    *,
    now: Optional[datetime] = None,
    reap_after: timedelta = AGENT_JOB_REAP_AFTER,
) -> int:
    """Fail in-flight agent jobs with no activity for `reap_after`.

    Returns the number of jobs reaped.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - reap_after
    minutes = int(reap_after.total_seconds() // 60)
    message = (
        f"Reaped by server: no agent activity for over {minutes} minutes "
        "(agent session lost; job orphaned)."
    )

    candidates = (
        db.query(AgentJob).filter(AgentJob.status.in_(ACTIVE_IN_FLIGHT_STATUSES)).all()
    )

    reaped = 0
    for job in candidates:
        if _job_activity_at(job) > cutoff:
            continue

        # Conditional write: only flip the job while it is still in-flight. A
        # concurrent completion/heartbeat may have finished it between the read
        # above and here — the WHERE guard makes the reaper lose that race
        # instead of clobbering a finished job (and its linked backup job).
        updated = (
            db.query(AgentJob)
            .filter(
                AgentJob.id == job.id,
                AgentJob.status.in_(ACTIVE_IN_FLIGHT_STATUSES),
            )
            .update(
                {
                    AgentJob.status: "failed",
                    AgentJob.completed_at: now,
                    AgentJob.updated_at: now,
                    AgentJob.error_message: message,
                },
                synchronize_session=False,
            )
        )
        if not updated:
            continue

        reaped += 1

        if job.backup_job_id:
            db.query(BackupJob).filter(
                BackupJob.id == job.backup_job_id,
                BackupJob.status.notin_(TERMINAL_BACKUP_STATUSES),
            ).update(
                {
                    BackupJob.status: "failed",
                    BackupJob.completed_at: now,
                    BackupJob.error_message: message,
                },
                synchronize_session=False,
            )

    if reaped:
        db.commit()
        logger.info(
            "Reaped orphaned agent jobs", count=reaped, reap_after_minutes=minutes
        )

    return reaped


def _reap_once() -> int:
    """One reap pass with its own session (runs in a worker thread)."""
    from app.utils.process_utils import (
        reconcile_orphaned_maintenance_jobs,
        reconcile_stale_backup_maintenance,
    )

    db = SessionLocal()
    try:
        reaped = reap_stale_agent_jobs(db)
        # Reconcile backup rows stuck in a running maintenance state whose
        # maintenance op died without writing a terminal status (startup-only
        # cleanup previously left these "running" until the next restart).
        reaped += reconcile_stale_backup_maintenance(db)
        # Fail maintenance *_jobs left 'pending' with no agent job to run them
        # (e.g. the agent job could not be queued under a db-lock) -- otherwise
        # they block the repository via admission control forever.
        reaped += reconcile_orphaned_maintenance_jobs(db)
        return reaped
    finally:
        db.close()


async def start_agent_job_reaper(
    interval_seconds: float = REAPER_INTERVAL_SECONDS,
) -> None:
    """Background loop that periodically reaps orphaned in-flight agent jobs."""
    logger.info(
        "Agent job reaper started",
        interval_seconds=interval_seconds,
        reap_after_minutes=int(AGENT_JOB_REAP_AFTER.total_seconds() // 60),
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            # Offload the synchronous DB work to a thread so a slow query never
            # blocks the event loop. The session is created and used inside the
            # thread (SQLite connections are thread-affine).
            await asyncio.to_thread(_reap_once)
        except asyncio.CancelledError:
            logger.info("Agent job reaper stopped")
            raise
        except Exception as exc:  # never let the loop die on a transient error
            logger.warning("Agent job reaper tick failed", error=str(exc))
