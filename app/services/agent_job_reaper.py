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

A `queued` job only reaches its agent over that agent's session, so one whose
agent never comes back would block the repository the same way. Those are
failed once the agent itself has been silent for `AGENT_OFFLINE_QUEUED_REAP_AFTER`;
a shorter absence (a laptop asleep overnight) keeps its jobs for the reconnect.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.core.agent_constants import AGENT_UPGRADE_TIMEOUT_SECONDS
from app.database.models import AgentJob, AgentMachine, Operation

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

# A queued job waits this long on an agent that has gone silent. Measured on
# the agent's last_seen_at, not the job's age: the job is delivered on the
# agent's next session, however old it is.
AGENT_OFFLINE_QUEUED_REAP_AFTER = timedelta(hours=24)

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
    failed_backup_job_ids: Optional[list[int]] = None,
) -> int:
    """Fail in-flight agent jobs with no activity for `reap_after`.

    Returns the number of jobs reaped. Backup jobs this pass flipped to failed
    are appended to `failed_backup_job_ids` (when given) so the caller can send
    failure notifications from an async context - the reaper is the only place
    an offline agent's job turns terminal, so no other path notifies for it.
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
        if _fail_agent_job(
            db,
            job,
            from_statuses=ACTIVE_IN_FLIGHT_STATUSES,
            now=now,
            message=message,
            failed_backup_job_ids=failed_backup_job_ids,
        ):
            reaped += 1

    if reaped:
        db.commit()
        logger.info(
            "Reaped orphaned agent jobs", count=reaped, reap_after_minutes=minutes
        )

    return reaped


def reap_queued_jobs_of_offline_agents(
    db: Session,
    *,
    now: Optional[datetime] = None,
    reap_after: timedelta = AGENT_OFFLINE_QUEUED_REAP_AFTER,
    failed_backup_job_ids: Optional[list[int]] = None,
) -> int:
    """Fail queued agent jobs whose agent has not been seen for `reap_after`.

    Every path that delivers a queued job needs the agent's session, so the
    job of an agent that never reconnects would otherwise stay queued and
    block its repository via admission control. The cutoff is compared in
    Python for the same naive-SQLite reason as _job_activity_at.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - reap_after
    minutes = int(reap_after.total_seconds() // 60)
    message = (
        f"Reaped by server: no agent activity for over {minutes} minutes "
        "(agent offline; job never delivered)."
    )

    candidates = (
        db.query(AgentJob, AgentMachine)
        .join(AgentMachine, AgentMachine.id == AgentJob.agent_machine_id)
        .filter(AgentJob.status == "queued")
        .all()
    )

    reaped = 0
    for job, agent in candidates:
        last_seen = agent.last_seen_at or agent.created_at
        if last_seen is not None and _as_utc(last_seen) > cutoff:
            continue
        # The agent may reconnect between the read above and the write: its
        # hello stamps last_seen_at before it dispatches the queued jobs.
        # Matching the value read here makes the reaper lose that race
        # instead of failing a job the returning agent is about to claim.
        still_silent = select(AgentMachine.id).where(
            AgentMachine.id == agent.id,
            AgentMachine.last_seen_at.is_(None)
            if agent.last_seen_at is None
            else AgentMachine.last_seen_at == agent.last_seen_at,
        )
        if _fail_agent_job(
            db,
            job,
            from_statuses=("queued",),
            now=now,
            message=message,
            failed_backup_job_ids=failed_backup_job_ids,
            also_where=(AgentJob.agent_machine_id.in_(still_silent),),
        ):
            reaped += 1

    if reaped:
        db.commit()
        logger.info(
            "Reaped queued jobs of offline agents",
            count=reaped,
            reap_after_minutes=minutes,
        )

    return reaped


def _fail_agent_job(
    db: Session,
    job: AgentJob,
    *,
    from_statuses: tuple[str, ...],
    now: datetime,
    message: str,
    failed_backup_job_ids: Optional[list[int]],
    also_where: tuple = (),
) -> bool:
    """Flip one job to failed, and its backup operation with it."""
    # Conditional write: only flip the job while it is still in the status the
    # caller read. A concurrent completion/heartbeat (or, for a queued job, a
    # dispatch that just claimed it) may have moved it between the read and
    # here — the WHERE guard makes the reaper lose that race instead of
    # clobbering the job (and its linked backup job).
    updated = (
        db.query(AgentJob)
        .filter(
            AgentJob.id == job.id,
            AgentJob.status.in_(from_statuses),
            *also_where,
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
        return False

    if job.operation_id:
        operation_failed = (
            db.query(Operation)
            .filter(
                Operation.id == job.operation_id,
                Operation.kind == "backup",
                Operation.status.notin_(tuple(TERMINAL_BACKUP_STATUSES)),
            )
            .update(
                {
                    Operation.status: "failed",
                    Operation.completed_at: now,
                    Operation.error_message: message,
                },
                synchronize_session=False,
            )
        )
        if operation_failed and failed_backup_job_ids is not None:
            failed_backup_job_ids.append(job.operation_id)

    return True


def reap_stale_agent_upgrades(
    db: Session,
    *,
    now: Optional[datetime] = None,
    timeout_seconds: int = AGENT_UPGRADE_TIMEOUT_SECONDS,
) -> int:
    """Mark upgrades whose endpoint never came back as failed.

    The agent cannot report the outcome of the thing that kills it, so this is
    the only path that resolves a failed upgrade. The cutoff is compared in
    Python rather than in the WHERE clause because the column is stored naive
    on SQLite, the same reason _job_activity_at exists.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=timeout_seconds)
    candidates = (
        db.query(AgentMachine)
        .filter(
            AgentMachine.upgrade_state == "requested",
            AgentMachine.upgrade_requested_at.isnot(None),
        )
        .all()
    )
    stale = [
        agent for agent in candidates if _as_utc(agent.upgrade_requested_at) < cutoff
    ]
    reaped = 0
    for agent in stale:
        # Conditional write, matching reap_stale_agent_jobs: the endpoint may
        # have re-registered on its target version between the read above and
        # here, which clears the state to idle. The WHERE guard makes the
        # reaper lose that race rather than overwrite a resolved upgrade with
        # a failure. requested_at is matched too, so a second upgrade
        # requested in that window is not failed on the first one's timeout.
        reaped += (
            db.query(AgentMachine)
            .filter(
                AgentMachine.id == agent.id,
                AgentMachine.upgrade_state == "requested",
                AgentMachine.upgrade_requested_at == agent.upgrade_requested_at,
            )
            .update(
                {
                    AgentMachine.upgrade_state: "failed",
                    AgentMachine.upgrade_error: (
                        "The endpoint did not come back on the target version "
                        "in time. Reinstall it manually from the reinstall "
                        "dialog."
                    ),
                    AgentMachine.updated_at: now,
                },
                synchronize_session=False,
            )
        )
    if reaped:
        db.commit()
        logger.info("Reaped stale agent upgrades", count=reaped)
    return reaped


def _reap_once(
    failed_backup_job_ids: Optional[list[int]] = None,
    reaped_operation_ids: Optional[list[int]] = None,
) -> int:
    """One reap pass with its own session (runs in a worker thread)."""
    from app.utils.process_utils import (
        reconcile_orphaned_maintenance_operations,
        reconcile_stale_backup_maintenance,
    )

    db = SessionLocal()
    try:
        reaped = reap_stale_agent_jobs(db, failed_backup_job_ids=failed_backup_job_ids)
        # A queued job whose agent has been gone for a day: no session is left
        # to deliver it, and admission control counts it as live work.
        reaped += reap_queued_jobs_of_offline_agents(
            db, failed_backup_job_ids=failed_backup_job_ids
        )
        # A `running` maintenance operation an inline caller handed to an
        # agent and never closed: with no agent job behind it, it would block
        # the repository via admission control until the next restart. Runs
        # before the backup-row pass below so the backup's maintenance state
        # is reconciled in the same tick.
        reaped += reconcile_orphaned_maintenance_operations(
            db, reaped_operation_ids=reaped_operation_ids
        )
        # Reconcile backup rows stuck in a running maintenance state whose
        # maintenance op died without writing a terminal status (startup-only
        # cleanup previously left these "running" until the next restart).
        reaped += reconcile_stale_backup_maintenance(db)
        # The agent cannot report the outcome of its own restart, so a request
        # nobody came back from is resolved here (spec section 7.1).
        reaped += reap_stale_agent_upgrades(db)
        return reaped
    finally:
        db.close()


async def _notify_reaped_backup_jobs(operation_ids: list[int]) -> None:
    """Send failure notifications for the backup operations the reaper just
    failed."""
    from app.services.agent_job_notifications import notify_backup_job_finished
    from app.services.operations.backup_facade import resolve_backup_job

    db = SessionLocal()
    try:
        for operation_id in operation_ids:
            backup_job = resolve_backup_job(db, operation_id)
            if backup_job is not None:
                await notify_backup_job_finished(db, backup_job)
    finally:
        db.close()


async def _release_upgrade_waves() -> None:
    """Advance the fleet upgrade waves with a session of our own."""
    # Imported here, not at module scope: the upgrade service is reached from
    # the API module, which imports this one.
    from app.services.agent_upgrades import release_agent_upgrade_waves

    db = SessionLocal()
    try:
        await release_agent_upgrade_waves(db)
    finally:
        db.close()


async def _broadcast_reaped_operations(operation_ids: list[int]) -> None:
    """Tell the operations feed about rows the reaper failed, the way every
    other writer of a terminal status does; the reap pass itself runs in a
    worker thread and cannot await."""
    from app.services.operations.events import broadcast_operation_updated

    db = SessionLocal()
    try:
        for operation_id in operation_ids:
            operation = db.get(Operation, operation_id)
            if operation is not None:
                await broadcast_operation_updated(operation, db)
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
            failed_backup_job_ids: list[int] = []
            reaped_operation_ids: list[int] = []
            await asyncio.to_thread(
                _reap_once, failed_backup_job_ids, reaped_operation_ids
            )
            if failed_backup_job_ids:
                await _notify_reaped_backup_jobs(failed_backup_job_ids)
            if reaped_operation_ids:
                await _broadcast_reaped_operations(reaped_operation_ids)
            # A slot frees when an endpoint leaves "requested", by success or
            # by the timeout reaped just above, so the next wave starts here
            # (spec section 8). This runs on the loop rather than in the
            # thread: it dispatches over the agent WebSocket.
            await _release_upgrade_waves()
        except asyncio.CancelledError:
            logger.info("Agent job reaper stopped")
            raise
        except Exception as exc:  # never let the loop die on a transient error
            logger.warning("Agent job reaper tick failed", error=str(exc))
