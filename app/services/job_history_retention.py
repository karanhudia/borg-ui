"""Retention for job history stored in the database.

Log *files* on disk already have retention (log_manager: age + total-size
caps), but the database side has none: every agent log line becomes an
agent_job_logs row, every finished job keeps its row (and often an inline
`logs` text copy) forever. Measured on real installs, agent_job_logs alone is
~90% of all rows, and on SQLite the file grows without bound.

The log save policy and two windows, all from SystemSettings and all
user-visible:

  log_save_policy         Applies to the database exactly as to the files:
                          log content of outcomes the policy does not keep
                          (e.g. clean successes under failed_and_warnings) is
                          dropped at the next pass regardless of age.

  log_retention_days      Log *content* older than this is dropped: agent
                          job log rows are deleted, inline `logs` columns are
                          cleared. Same window the log files use, so the DB
                          copy never outlives the file it mirrors.
  cleanup_retention_days  Job *rows* older than this are deleted — every kind
                          of job record, plan runs and script executions
                          included, regardless of status (see _older_than for
                          why that is safe). Not optional by design: an
                          unbounded job table is never what anyone wants, so
                          only the window moves.

Deletes are chunked so SQLite never holds a giant transaction;
DB-level FK actions (agent_job_logs CASCADE, script_executions CASCADE,
various SET NULL) handle the children — SQLite connections run with
PRAGMA foreign_keys=ON (see database.py).

Note for SQLite operators: DELETE frees pages for reuse but does not shrink
the file; the manual cleanup endpoint runs VACUUM for that.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, Optional

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.log_policy import DEFAULT_LOG_SAVE_POLICY, LOG_SAVE_POLICIES

from app.database.models import (
    AgentJob,
    AgentJobLog,
    BackupJob,
    BackupJobRetryLineage,
    BackupPlanRun,
    CheckJob,
    CompactJob,
    DeleteArchiveJob,
    PackageInstallJob,
    PruneJob,
    RcloneSyncJob,
    RepositoryWipeJob,
    RestoreCheckJob,
    RestoreJob,
    ScriptExecution,
    SystemSettings,
    utc_now,
)

logger = structlog.get_logger()

# Rows deleted / updated per transaction. Keeps SQLite write transactions (and
# their locks) short; Postgres does not care either way.
CHUNK_SIZE = 1000

DEFAULT_LOG_RETENTION_DAYS = 30
DEFAULT_CLEANUP_RETENTION_DAYS = 90

# Job-history tables whose rows fall with cleanup_retention_days — every kind
# of job record, including plan runs and script executions. Deleting a plan
# run cascades its run-repository links and hook executions at the DB level.
# (model, inline log columns cleared at log_retention_days)
_JOB_TABLES = (
    (AgentJob, ()),
    (BackupJob, ("logs",)),
    (RestoreJob, ("logs",)),
    (CheckJob, ("logs",)),
    (RestoreCheckJob, ("logs",)),
    (CompactJob, ("logs",)),
    (PruneJob, ("logs",)),
    (DeleteArchiveJob, ("logs",)),
    (RepositoryWipeJob, ("logs",)),
    (RcloneSyncJob, ("log_text",)),
    (PackageInstallJob, ("stdout", "stderr")),
    (ScriptExecution, ("stdout", "stderr")),
    (BackupPlanRun, ()),
)


def _older_than(model, cutoff):
    """Filter: last known activity older than cutoff — regardless of status.

    Nothing outlives the window by design: a job whose status claims it is
    still in flight but that has not moved for the whole retention period is a
    zombie (e.g. queued for an agent that never returned), not history worth
    keeping. Genuinely live work never looks old, because age is taken from
    the freshest timestamp the table has: completed_at, then updated_at
    (refreshed on every agent log line), then started_at, then created_at.
    """
    columns = [model.completed_at]
    if hasattr(model, "updated_at"):
        columns.append(model.updated_at)
    if hasattr(model, "started_at"):
        columns.append(model.started_at)
    if hasattr(model, "created_at"):
        columns.append(model.created_at)
    return (func.coalesce(*columns) < cutoff,)


def _delete_chunked(db: Session, model, filters) -> int:
    """Delete matching rows in CHUNK_SIZE batches, committing per batch."""
    total = 0
    while True:
        ids = [row[0] for row in db.query(model.id).filter(*filters).limit(CHUNK_SIZE)]
        if not ids:
            return total
        db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        total += len(ids)


def purge_agent_job_logs(db: Session, filters) -> int:
    """Delete agent_job_logs rows of jobs matching the given AgentJob filters."""
    total = 0
    while True:
        ids = [
            row[0]
            for row in db.query(AgentJobLog.id)
            .join(AgentJob, AgentJobLog.agent_job_id == AgentJob.id)
            .filter(*filters)
            .limit(CHUNK_SIZE)
        ]
        if not ids:
            return total
        db.query(AgentJobLog).filter(AgentJobLog.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()
        total += len(ids)


def clear_inline_job_logs(db: Session, make_filters) -> int:
    """NULL the inline `logs`-style columns of jobs matching make_filters(model).

    History, stats and error_message stay; only the bulky captured output goes.
    has_logs is cleared where present so the UI stops advertising logs that no
    longer exist anywhere.
    """
    total = 0
    for model, log_columns in _JOB_TABLES:
        if not log_columns:
            continue
        first = getattr(model, log_columns[0])
        values = {column: None for column in log_columns}
        if hasattr(model, "has_logs"):
            values["has_logs"] = False
        while True:
            ids = [
                row[0]
                for row in db.query(model.id)
                .filter(*make_filters(model), first.isnot(None))
                .limit(CHUNK_SIZE)
            ]
            if not ids:
                break
            db.query(model).filter(model.id.in_(ids)).update(
                values, synchronize_session=False
            )
            db.commit()
            total += len(ids)
    return total


def purge_job_rows(db: Session, cutoff) -> int:
    """Delete finished job rows older than cutoff (all job tables)."""
    total = 0
    for model, _ in _JOB_TABLES:
        total += _delete_chunked(db, model, _older_than(model, cutoff))
    # Retry lineage rows carry only SET NULL pointers at their jobs; once the
    # jobs of their era are gone the husks serve nothing. Same window.
    total += _delete_chunked(
        db,
        BackupJobRetryLineage,
        (BackupJobRetryLineage.requested_at < cutoff,),
    )
    return total


def _policy_discarded_statuses(policy: str) -> tuple:
    """Job statuses whose log content the save policy does not want kept.

    Mirrors log_policy's read-side semantics on the write side: under
    failed_only, success and warning outcomes lose their logs; under
    failed_and_warnings only clean successes do; all_jobs keeps everything
    until the age windows. Failed/cancelled/unknown statuses are never
    policy-discarded.
    """
    if policy == "failed_only":
        return ("completed", "completed_with_warnings")
    if policy == "failed_and_warnings":
        return ("completed",)
    return ()


def run_retention(db: Session, settings: Optional[SystemSettings] = None) -> Dict:
    """Apply the save policy and both retention windows. Returns per-phase counts."""
    if settings is None:
        settings = db.query(SystemSettings).first()

    log_days = getattr(settings, "log_retention_days", None) or (
        DEFAULT_LOG_RETENTION_DAYS
    )
    row_days = getattr(settings, "cleanup_retention_days", None) or (
        DEFAULT_CLEANUP_RETENTION_DAYS
    )
    policy = getattr(settings, "log_save_policy", None)
    if policy not in LOG_SAVE_POLICIES:
        policy = DEFAULT_LOG_SAVE_POLICY
    discarded = _policy_discarded_statuses(policy)

    now = utc_now()
    log_cutoff = now - timedelta(days=log_days)
    results = {
        "agent_log_rows_deleted": purge_agent_job_logs(
            db, _older_than(AgentJob, log_cutoff)
        ),
        "inline_logs_cleared": clear_inline_job_logs(
            db, lambda model: _older_than(model, log_cutoff)
        ),
        # The log save policy applies to the database exactly as it does to
        # the log files: content the policy does not want is dropped at the
        # next pass, no matter how young.
        "policy_log_rows_deleted": (
            purge_agent_job_logs(db, (AgentJob.status.in_(discarded),))
            if discarded
            else 0
        ),
        "policy_inline_logs_cleared": (
            clear_inline_job_logs(db, lambda model: (model.status.in_(discarded),))
            if discarded
            else 0
        ),
        "job_rows_deleted": purge_job_rows(db, now - timedelta(days=row_days)),
    }
    if any(results.values()):
        logger.info(
            "Job history retention applied",
            log_retention_days=log_days,
            cleanup_retention_days=row_days,
            log_save_policy=policy,
            **results,
        )
    return results


def run_retention_once() -> Dict:
    """Session-owning wrapper for the scheduler / endpoint."""
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        return run_retention(db)
    finally:
        db.close()


async def start_job_history_retention(
    interval_seconds: float = 24 * 3600.0,
    initial_delay_seconds: float = 300.0,
) -> None:
    """Background loop: apply retention shortly after startup, then daily."""
    import asyncio

    logger.info(
        "Job history retention scheduler started",
        interval_seconds=interval_seconds,
        initial_delay_seconds=initial_delay_seconds,
    )
    delay = initial_delay_seconds
    while True:
        try:
            await asyncio.sleep(delay)
            # Sync DB work off the event loop; the session lives in the thread
            # (SQLite connections are thread-affine).
            await asyncio.to_thread(run_retention_once)
        except asyncio.CancelledError:
            logger.info("Job history retention scheduler stopped")
            raise
        except Exception as exc:  # never let the loop die on a transient error
            logger.warning("Job history retention tick failed", error=str(exc))
        delay = interval_seconds
