"""
Utility functions for process management and orphan detection
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional
import structlog
from datetime import datetime, timedelta
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, object_session
from app.config import settings
from app.core.borg_router import BorgRouter
from app.utils.borg_env import (
    cleanup_temp_key_file,
    effective_repository_remote_path,
    get_standard_ssh_opts,
)
from app.database.models import (
    AgentJob,
    BackupPlanRun,
    BackupPlanRunRepository,
    CheckJob,
    CompactJob,
    BackupJob,
    DeleteArchiveJob,
    Operation,
    PruneJob,
    RestoreCheckJob,
    RestoreJob,
    Repository,
)
from app.services.operations.backup_facade import backup_jobs_in_maintenance
from app.utils.backup_maintenance import (
    COMPLETED_BACKUP_STATUSES,
    RUNNING_BACKUP_MAINTENANCE_FAILURES,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
    resolve_repository_ssh_connection,
)

logger = structlog.get_logger()

ACTIVE_JOB_STATUSES = {"pending", "running"}
ACTIVE_PLAN_RUN_STATUSES = {"pending", "running"}
SUCCESS_PLAN_REPOSITORY_STATUSES = {"completed", "completed_with_warnings"}
WARNING_PLAN_REPOSITORY_STATUSES = {"completed_with_warnings", "skipped"}
CONTAINER_RESTARTED_DURING_BACKUP = json.dumps(
    {"key": "backend.errors.service.containerRestartedDuringBackup"}
)
CONTAINER_RESTARTED_DURING_OPERATION = json.dumps(
    {"key": "backend.errors.service.containerRestartedDuringOperation"}
)


def _plan_repository_failed(status: Optional[str]) -> bool:
    return (
        status not in SUCCESS_PLAN_REPOSITORY_STATUSES
        and status not in WARNING_PLAN_REPOSITORY_STATUSES
    )


def _fail_backup_plan_child_after_restart(
    child: BackupPlanRunRepository, now: datetime, message: str
) -> None:
    child.status = "failed"
    child.completed_at = child.completed_at or now
    child.error_message = child.error_message or message


def _finalize_interrupted_backup_plan_run(
    run: BackupPlanRun, now: datetime, message: str
) -> None:
    statuses = [child.status for child in run.repositories]

    if not statuses:
        run.status = "failed"
        run.error_message = run.error_message or message
    else:
        has_success = any(
            status in SUCCESS_PLAN_REPOSITORY_STATUSES for status in statuses
        )
        has_cancelled = any(status == "cancelled" for status in statuses)
        has_failure = any(_plan_repository_failed(status) for status in statuses)
        has_warning = any(
            status in WARNING_PLAN_REPOSITORY_STATUSES for status in statuses
        )

        if has_cancelled and not has_success:
            run.status = "cancelled"
        elif has_success and (has_failure or has_cancelled):
            run.status = "partial"
        elif has_failure:
            run.status = "failed"
        elif has_warning:
            run.status = "completed_with_warnings"
        else:
            run.status = "completed"

        if run.status in {"failed", "partial"}:
            run.error_message = run.error_message or message

    run.completed_at = run.completed_at or now


def _normalize_interrupted_backup_plan_runs(
    db: Session,
    now: datetime,
    interrupted_runs: Optional[list[BackupPlanRun]] = None,
) -> int:
    """Finish active backup plan run rows that cannot resume after a restart."""
    if interrupted_runs is None:
        interrupted_runs = (
            db.query(BackupPlanRun)
            .filter(BackupPlanRun.status.in_(ACTIVE_PLAN_RUN_STATUSES))
            .all()
        )

    for run in interrupted_runs:
        for child in run.repositories:
            if child.status in ACTIVE_PLAN_RUN_STATUSES:
                _fail_backup_plan_child_after_restart(
                    child, now, CONTAINER_RESTARTED_DURING_BACKUP
                )

        _finalize_interrupted_backup_plan_run(
            run, now, CONTAINER_RESTARTED_DURING_BACKUP
        )

        logger.info(
            "Normalized interrupted backup plan run after restart",
            backup_plan_run_id=run.id,
            backup_plan_id=run.backup_plan_id,
            status=run.status,
        )

    return len(interrupted_runs)


def _mark_backup_job_failed_after_restart(
    job: BackupJob, now: datetime, message: str
) -> None:
    job.status = "failed"
    job.error_message = message
    job.completed_at = now


def _has_running_check_child(db: Session, backup_job: BackupJob) -> bool:
    # Phase 5 moved check to `operations`, so a live check child is normally an
    # operation now. The legacy table is still consulted for a row a pre-phase-5
    # process left running; both are deleted in phase 9.
    if backup_job.repository_id is not None:
        from app.database.models import Operation

        running_operation = (
            db.query(Operation.id)
            .filter(
                Operation.kind == "check",
                Operation.status == "running",
                Operation.repository_id == backup_job.repository_id,
            )
            .first()
        )
        if running_operation is not None:
            return True

    query = db.query(CheckJob.id).filter(CheckJob.status == "running")
    if backup_job.repository_id is not None:
        query = query.filter(CheckJob.repository_id == backup_job.repository_id)
    else:
        query = query.filter(CheckJob.repository_path == backup_job.repository)
    return query.first() is not None


def _mark_backup_maintenance_failed(
    backup_job: BackupJob,
    previous_state: str,
    now: datetime,
) -> None:
    backup_job.completed_at = backup_job.completed_at or now
    if backup_job.status not in COMPLETED_BACKUP_STATUSES:
        backup_job.status = "failed"
        backup_job.error_message = (
            backup_job.error_message or CONTAINER_RESTARTED_DURING_OPERATION
        )
    backup_job.maintenance_status = RUNNING_BACKUP_MAINTENANCE_FAILURES[previous_state]


def _mark_stale_backup_maintenance_failed(db: Session, now: datetime) -> int:
    """
    Normalize backup rows left in running maintenance states after a restart.

    This handles stale backup rows even when the corresponding maintenance
    child job row is already gone or no longer marked as running.
    """
    stale_backup_jobs = backup_jobs_in_maintenance(db)

    normalized_count = 0
    for backup_job in stale_backup_jobs:
        previous_state = backup_job.maintenance_status
        if previous_state == "running_check" and _has_running_check_child(
            db, backup_job
        ):
            continue

        _mark_backup_maintenance_failed(backup_job, previous_state, now)
        normalized_count += 1
        logger.info(
            "Normalized stale backup maintenance state after restart",
            backup_job_id=backup_job.id,
            repository=backup_job.repository,
            previous_maintenance_status=previous_state,
            new_maintenance_status=backup_job.maintenance_status,
        )

    return normalized_count


# A backup row stuck in a running maintenance state for longer than this (with no
# live child job) is reconciled at runtime. Kept generous so genuinely-running
# maintenance whose child row is written a moment later is never killed; the
# liveness guard below is the primary protection.
MAINTENANCE_RECONCILE_AFTER = timedelta(minutes=5)

_MAINTENANCE_CHILD_MODELS = {
    "running_prune": PruneJob,
    "running_compact": CompactJob,
    "running_check": CheckJob,
}

# Phase 5 moved prune, compact, and check onto `operations`; the post-backup
# inline path (`start_inline_maintenance`) writes a `running` Operation row
# for the whole synchronous run, which the legacy tables below never see.
_MAINTENANCE_STATUS_KIND = {
    "running_prune": "prune",
    "running_compact": "compact",
    "running_check": "check",
}


def _has_running_maintenance_child(
    db: Session, backup_job: BackupJob, maintenance_status: str
) -> bool:
    """True if a maintenance child job for this repo is still actually running.

    The PruneJob/CompactJob/CheckJob row is created and set to 'running' for both
    server-side and agent-delegated maintenance, so it is a reliable liveness
    signal. Agent maintenance jobs carry no backup_job_id, so we correlate by
    repository (mirroring _has_running_check_child).
    """
    kind = _MAINTENANCE_STATUS_KIND.get(maintenance_status)
    if (
        kind is not None
        and backup_job.repository_id is not None
        and db.query(Operation.id)
        .filter(
            Operation.repository_id == backup_job.repository_id,
            Operation.kind == kind,
            Operation.status == "running",
        )
        .first()
        is not None
    ):
        return True
    model = _MAINTENANCE_CHILD_MODELS.get(maintenance_status)
    if model is None:
        return False
    query = db.query(model.id).filter(model.status == "running")
    if backup_job.repository_id is not None:
        query = query.filter(model.repository_id == backup_job.repository_id)
    else:
        query = query.filter(model.repository_path == backup_job.repository)
    return query.first() is not None


def _strip_tz(value: datetime) -> datetime:
    """Drop tzinfo so a possibly-aware DB value compares with naive utcnow()."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def reconcile_stale_backup_maintenance(
    db: Session,
    *,
    now: Optional[datetime] = None,
    reap_after: timedelta = MAINTENANCE_RECONCILE_AFTER,
) -> int:
    """Normalize backup rows stuck in a running maintenance state, at RUNTIME.

    ``_mark_stale_backup_maintenance_failed`` runs only at startup and assumes
    nothing is live. This runs periodically, so it must not kill genuinely
    running maintenance: it skips any row whose maintenance child job is still
    'running', and only reaps rows older than ``reap_after``.

    This closes the gap where an agent-delegated maintenance op fails without
    writing a terminal ``maintenance_status`` -- the child job reaper only fires
    on a 'running' child, and the agent-job reaper propagates via backup_job_id
    (which repository maintenance jobs do not carry). Returns the count reaped.
    """
    # Normalize to naive UTC so the age comparison holds even if a caller passes
    # a tz-aware `now` (DB datetimes are naive UTC).
    now = _strip_tz(now or datetime.utcnow())
    cutoff = now - reap_after

    stuck = backup_jobs_in_maintenance(db)

    reaped = 0
    for backup_job in stuck:
        state = backup_job.maintenance_status
        # 1) genuinely in-progress maintenance -> leave alone
        if _has_running_maintenance_child(db, backup_job, state):
            continue
        # 2) age guard (BackupJob has no updated_at; completed_at is set when the
        #    backup phase finished, i.e. before maintenance started)
        activity = backup_job.completed_at or backup_job.created_at
        if activity is not None and _strip_tz(activity) > cutoff:
            continue
        _mark_backup_maintenance_failed(backup_job, state, now)
        reaped += 1
        logger.info(
            "Reconciled stale backup maintenance state at runtime",
            backup_job_id=backup_job.id,
            repository=backup_job.repository,
            previous_maintenance_status=state,
            new_maintenance_status=backup_job.maintenance_status,
        )

    if reaped:
        db.commit()

    return reaped


# An agent maintenance job carries no backup_job_id, so a *_job is correlated to
# its agent job via the payload's maintenance_job {kind, id}.
_ACTIVE_AGENT_STATUSES = ("queued", "claimed", "cancel_requested", "running")
_ORPHAN_MAINTENANCE_MODELS = (
    ("prune", PruneJob),
    ("compact", CompactJob),
    ("check", CheckJob),
    ("delete_archive", DeleteArchiveJob),
)


def active_agent_maintenance_jobs(db: Session) -> set[tuple[str, str, int]]:
    """The `(table, kind, id)` of every maintenance job a live agent job is
    carrying, read once so a reap pass can check many rows against it.
    `operations` ids and the legacy `*_jobs` ids are separate sequences. A
    payload that names no table predates the marker and may refer to
    either (a pre-phase-5 legacy row, or an operation queued by the build
    before this one), so it counts for both: an ambiguous reference keeps
    a row alive rather than reaping a live one."""
    from app.services.operations.job_facade import LEGACY_MODELS

    active = (
        db.query(AgentJob.payload)
        .filter(
            AgentJob.job_type == "repository",
            AgentJob.status.in_(_ACTIVE_AGENT_STATUSES),
        )
        .all()
    )
    refs: set[tuple[str, str, int]] = set()
    for (payload,) in active:
        operation = payload.get("operation") if isinstance(payload, dict) else None
        maintenance_job = (
            operation.get("maintenance_job") if isinstance(operation, dict) else None
        )
        if not isinstance(maintenance_job, dict):
            continue
        kind, job_id = maintenance_job.get("kind"), maintenance_job.get("id")
        if not kind or job_id is None:
            continue
        table = maintenance_job.get("table")
        if table:
            refs.add((table, kind, job_id))
            continue
        refs.add((Operation.__tablename__, kind, job_id))
        model = LEGACY_MODELS.get(kind)
        if model is not None:
            refs.add((model.__tablename__, kind, job_id))
    return refs


def has_active_agent_job_for(
    db: Session, maintenance_kind: str, maintenance_job_id: int, *, table: str
) -> bool:
    """True if a live agent job exists for this maintenance job: an
    `operations` row or a legacy ``*_job``, as `table` says."""
    return (
        table,
        maintenance_kind,
        maintenance_job_id,
    ) in active_agent_maintenance_jobs(db)


def reconcile_orphaned_maintenance_jobs(
    db: Session,
    *,
    now: Optional[datetime] = None,
    reap_after: timedelta = MAINTENANCE_RECONCILE_AFTER,
) -> int:
    """Fail maintenance ``*_jobs`` left 'pending' with no agent job to run them.

    The ``*_job`` row (PruneJob/CompactJob/CheckJob/DeleteArchiveJob) is created
    before its agent job is queued; if the queue fails (e.g. ``database is
    locked``) no agent job exists, so the row stays 'pending' forever and blocks
    the repository via admission control. Reap old pending rows that have no
    active agent job.

    Only 'pending' is reaped here: 'running' rows are covered by the existing
    process-liveness reapers, and a server-side maintenance op runs in-process
    without an agent job (so absence of an agent job does not imply orphaned for
    a running row). The age guard bounds a legitimately just-created row.
    """
    now = _strip_tz(now or datetime.utcnow())
    cutoff = now - reap_after

    reaped = 0
    for kind, model in _ORPHAN_MAINTENANCE_MODELS:
        candidates = (
            db.query(model.id, model.created_at, model.repository_id)
            .filter(model.status == "pending")
            .all()
        )
        for job_id, created_at, repository_id in candidates:
            if created_at is not None and _strip_tz(created_at) > cutoff:
                continue  # too fresh; its agent job may be queued a moment later
            if has_active_agent_job_for(db, kind, job_id, table=model.__tablename__):
                continue  # dispatched, waiting for the agent
            # Fail closed with a guarded UPDATE: it only touches a row that is
            # STILL 'pending', so a concurrent dispatch that has meanwhile moved
            # it to 'running' is left untouched. A load-then-mutate would instead
            # overwrite that live transition on commit. coalesce keeps any
            # error_message/completed_at already set.
            updated = (
                db.query(model)
                .filter(model.id == job_id, model.status == "pending")
                .update(
                    {
                        model.status: "failed",
                        model.error_message: func.coalesce(
                            model.error_message,
                            "orphaned: no agent job was queued for this maintenance",
                        ),
                        model.completed_at: func.coalesce(model.completed_at, now),
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                continue  # another transaction claimed the row first
            # Re-check correlation now the row is claimed: an agent job could have
            # been queued between the check above and this UPDATE (status was
            # still 'pending' then). If so, preserve the dispatched job by
            # reverting rather than committing a spurious 'failed'.
            if has_active_agent_job_for(db, kind, job_id, table=model.__tablename__):
                db.rollback()
                continue
            db.commit()
            reaped += 1
            logger.info(
                "Reaped orphaned pending maintenance job",
                job_model=model.__name__,
                job_id=job_id,
                repository_id=repository_id,
            )

    return reaped


def reconcile_orphaned_maintenance_operations(
    db: Session,
    *,
    now: Optional[datetime] = None,
    reap_after: timedelta = MAINTENANCE_RECONCILE_AFTER,
    reaped_operation_ids: Optional[list[int]] = None,
) -> int:
    """Fail `running` maintenance operations of agent-executed repositories
    that no agent job is working on.

    A caller that runs maintenance inline (post-backup prune, compact, check)
    creates the operation `running` and hands it to the agent; when the agent
    job is refused or lost, only that caller could close the row. If it does
    not, the operation counts as active write work and every backup of the
    repository is refused until a restart. Startup recovery applies this
    rule to every row; at runtime it is safe only where liveness is provable,
    which is the agent case: the agent job carries the operation's id, so a
    `running` operation with no live agent job has nothing behind it. The
    executor is read from the row (`execution_mode`, recorded when the
    inline operation was created), not from the repository's current
    setting. A server-side operation is left alone: the Borg process runs
    in this process, a prune records no pid, and the runner's own tasks
    carry no marker on the row. The age guard covers the moment between
    creating the row and queueing its agent job. The ids of the rows it
    failed are appended to `reaped_operation_ids` (when given) so the caller,
    which runs this in a worker thread, can broadcast the change from the
    event loop.
    """
    from app.services.operations.job_facade import MAINTENANCE_KINDS
    from app.services.operations.runner import operation_runner

    now = _strip_tz(now or datetime.utcnow())
    cutoff = now - reap_after

    candidates = (
        db.query(
            Operation.id,
            Operation.kind,
            Operation.repository_id,
            Operation.started_at,
            Operation.created_at,
        )
        .filter(
            Operation.kind.in_(MAINTENANCE_KINDS),
            Operation.status == "running",
            Operation.execution_mode == "agent",
            Operation.process_pid.is_(None),
        )
        .all()
    )
    if not candidates:
        return 0
    live = active_agent_maintenance_jobs(db)
    reaped = 0
    for operation_id, kind, repository_id, started_at, created_at in candidates:
        started = started_at or created_at
        if started is not None and _strip_tz(started) > cutoff:
            continue  # its agent job may be queued a moment later
        if operation_id in operation_runner.running_tasks:
            continue  # the runner is executing it in this process
        if (Operation.__tablename__, kind, operation_id) in live:
            continue  # dispatched, the agent is on it
        # Guarded UPDATE, same shape as the legacy pass above: only a row that
        # is still `running` is touched, so a caller that closed it meanwhile
        # keeps its own terminal status. A locked database on one row must
        # not end the pass for the others.
        try:
            updated = (
                db.query(Operation)
                .filter(Operation.id == operation_id, Operation.status == "running")
                .update(
                    {
                        Operation.status: "failed",
                        Operation.error_message: func.coalesce(
                            Operation.error_message,
                            "orphaned: no agent job is working on this operation",
                        ),
                        Operation.completed_at: func.coalesce(
                            Operation.completed_at, now
                        ),
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                db.rollback()  # closed by its caller between the read and the update
                continue
            if has_active_agent_job_for(
                db, kind, operation_id, table=Operation.__tablename__
            ):
                db.rollback()  # queued between the read and the update
                continue
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Could not reap an orphaned maintenance operation",
                operation_id=operation_id,
                kind=kind,
                error=str(exc),
            )
            continue
        reaped += 1
        if reaped_operation_ids is not None:
            reaped_operation_ids.append(operation_id)
        logger.info(
            "Reaped orphaned running maintenance operation",
            operation_id=operation_id,
            kind=kind,
            repository_id=repository_id,
        )

    return reaped


def is_process_alive(pid: int, stored_start_time: int) -> bool:
    """
    Check if a process with given PID and start_time is still running

    Args:
        pid: Process ID to check
        stored_start_time: Start time in jiffies when process was created

    Returns:
        True if process is alive and matches stored start_time
        False if process is dead OR PID was reused by different process
    """
    if not pid or not stored_start_time:
        return False

    try:
        # Try to read /proc/[pid]/stat
        with open(f"/proc/{pid}/stat", "r") as f:
            stat_data = f.read()

        # Extract current start_time
        # Format: pid (comm) state ppid ... starttime (22nd field)
        fields = stat_data.split(")")[1].split()
        current_start_time = int(fields[19])

        # Compare with stored start_time
        if current_start_time == stored_start_time:
            # Same process! It's still alive
            return True
        else:
            # PID was reused by a different process
            logger.info(
                "PID reused by different process",
                pid=pid,
                stored_start_time=stored_start_time,
                current_start_time=current_start_time,
            )
            return False

    except FileNotFoundError:
        # /proc/[pid] doesn't exist - process is dead
        logger.info("Process not found in /proc", pid=pid)
        return False
    except Exception as e:
        logger.error("Error checking process", pid=pid, error=str(e))
        return False


def break_repository_lock(repository: Repository) -> bool:
    """
    Break the lock on a repository

    Args:
        repository: Repository model instance

    Returns:
        True if lock was successfully broken, False otherwise
    """
    temp_key_file = None
    try:
        try:
            db = object_session(repository)
        except Exception:
            db = None
        connection = resolve_repository_ssh_connection(repository, db) if db else None
        cmd = BorgRouter(repository).build_break_lock_command(
            repository_path=repository.path,
            remote_path=effective_repository_remote_path(repository, db),
        )

        # Set environment variables
        env = os.environ.copy()
        if repository.passphrase:
            env["BORG_PASSPHRASE"] = repository.passphrase

        # For remote repos, use the same resolved connection for the Borg
        # remote command and SSH identity, including legacy ssh:// URLs.
        if connection:
            temp_key_file = resolve_repo_ssh_key_file(repository, db)
            ssh_opts = get_standard_ssh_opts(
                include_key_path=temp_key_file, connection=connection, db=db
            )
            env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"
        elif repository.connection_id:
            # The connection could not be resolved here, usually because the
            # repository arrived without a session. Its id is enough to load
            # the row and honour its pinned host key, which beats connecting
            # to a pinned host with verification turned down.
            ssh_opts = get_standard_ssh_opts(connection_id=repository.connection_id)
            env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"

        # Execute break-lock command
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            logger.info(
                "Successfully broke repository lock",
                repository_id=repository.id,
                repository_path=repository.path,
            )
            return True
        else:
            logger.error(
                "Failed to break repository lock",
                repository_id=repository.id,
                returncode=result.returncode,
                stderr=result.stderr,
            )
            return False

    except Exception as e:
        logger.error(
            "Error breaking repository lock", repository_id=repository.id, error=str(e)
        )
        return False
    finally:
        cleanup_temp_key_file(temp_key_file)


def _is_remote_repository(repository: Repository, db: Session) -> bool:
    """Return whether a repository may still have a live remote Borg process."""
    path = getattr(repository, "path", "") or ""
    repository_type = (getattr(repository, "repository_type", "") or "").lower()
    return bool(
        resolve_repository_ssh_connection(repository, db)
        or getattr(repository, "connection_id", None)
        or repository_type == "ssh"
        or path.startswith("ssh://")
    )


def cleanup_orphaned_jobs(db: Session):
    """
    Find and cleanup jobs that were running when container stopped

    This function is called on container startup to detect and cleanup
    orphaned jobs from container restarts or crashes.

    Args:
        db: Database session
    """
    logger.info("Checking for orphaned jobs...")

    now = datetime.utcnow()
    stale_backup_jobs = _mark_stale_backup_maintenance_failed(db, now)

    # Backup rows written before phase 8 moved backup to `operations`. New
    # work is recovered by OperationRunner.recover_on_startup (spec 7.6),
    # which fails them the same way, since a backup records no pid. Empty
    # after the first restart past the upgrade; goes away in phase 9.
    active_backup_jobs = (
        db.query(BackupJob).filter(BackupJob.status.in_(ACTIVE_JOB_STATUSES)).all()
    )

    # Find all running restore jobs
    running_restore_jobs = (
        db.query(RestoreJob).filter(RestoreJob.status == "running").all()
    )

    # Running check rows written before phase 5 moved check to `operations`.
    # New work is recovered by OperationRunner.recover_on_startup (spec 7.6),
    # which also makes the local lock-break attempt this loop makes below. This
    # query is empty on any install that has restarted since the upgrade, and
    # goes away with the table in phase 9.
    running_check_jobs = db.query(CheckJob).filter(CheckJob.status == "running").all()

    # Running restore-check rows written before phase 5 moved restore_check to
    # `operations`, kept for the same reason as running_check_jobs above.
    # Empty after the first restart past the upgrade; goes away with the
    # table in phase 9.
    running_restore_check_jobs = (
        db.query(RestoreCheckJob).filter(RestoreCheckJob.status == "running").all()
    )

    # Running prune rows written before phase 5 moved prune to `operations`,
    # kept for the same reason as running_check_jobs above: OperationRunner.
    # recover_on_startup covers new work, but a pre-upgrade running row still
    # needs this loop to mark it failed. Empty after the first restart past
    # the upgrade; goes away with the table in phase 9.
    running_prune_jobs = db.query(PruneJob).filter(PruneJob.status == "running").all()

    # Running compact rows written before phase 5 moved compact to
    # `operations`, kept for the same reason as running_check_jobs and
    # running_prune_jobs above. Empty after the first restart past the
    # upgrade; goes away with the table in phase 9.
    running_compact_jobs = (
        db.query(CompactJob).filter(CompactJob.status == "running").all()
    )

    active_backup_plan_runs = (
        db.query(BackupPlanRun)
        .filter(BackupPlanRun.status.in_(ACTIVE_PLAN_RUN_STATUSES))
        .all()
    )

    total_jobs = (
        len(active_backup_jobs)
        + len(running_restore_jobs)
        + len(running_check_jobs)
        + len(running_restore_check_jobs)
        + len(running_prune_jobs)
        + len(running_compact_jobs)
        + stale_backup_jobs
        + len(active_backup_plan_runs)
    )
    logger.info(
        "Found running jobs",
        backup_jobs=len(active_backup_jobs),
        restore_jobs=len(running_restore_jobs),
        check_jobs=len(running_check_jobs),
        restore_check_jobs=len(running_restore_check_jobs),
        prune_jobs=len(running_prune_jobs),
        compact_jobs=len(running_compact_jobs),
        stale_backup_maintenance_jobs=stale_backup_jobs,
        active_backup_plan_runs=len(active_backup_plan_runs),
    )

    if total_jobs == 0:
        logger.info("No orphaned jobs found")
        return

    # Process backup jobs
    for job in active_backup_jobs:
        # Backup jobs don't have process_pid tracking, so active rows cannot resume.
        previous_status = job.status
        _mark_backup_job_failed_after_restart(
            job, now, CONTAINER_RESTARTED_DURING_BACKUP
        )

        logger.info(
            "Orphaned backup job detected",
            job_id=job.id,
            repository=job.repository,
            previous_status=previous_status,
        )

    # Process restore jobs
    for job in running_restore_jobs:
        # Rows written before phase 7 moved restore to `operations`. New
        # restores are recovered by OperationRunner.recover_on_startup (spec
        # 7.6), which fails them the same way: a restore records no pid to
        # reattach to. Empty after the first restart past the upgrade; goes
        # away with the table in phase 9.
        job.status = "failed"
        job.error_message = json.dumps(
            {"key": "backend.errors.service.containerRestartedDuringRestore"}
        )
        job.completed_at = datetime.utcnow()

        logger.info(
            "Orphaned restore job detected", job_id=job.id, repository=job.repository
        )

    # Process check jobs
    for job in running_check_jobs:
        if not is_process_alive(job.process_pid, job.process_start_time):
            # Process is dead! Mark job as failed
            job.status = "failed"
            job.error_message = CONTAINER_RESTARTED_DURING_OPERATION
            job.completed_at = now

            logger.info(
                "Orphaned check job detected",
                job_id=job.id,
                repository_id=job.repository_id,
                pid=job.process_pid,
            )

            # Get repository to determine if we should auto-break lock
            repository = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )

            if repository:
                if not _is_remote_repository(repository, db):
                    # For local repos, we can safely break the lock
                    logger.info(
                        "Attempting to break lock for local repository",
                        repository_id=repository.id,
                    )
                    if break_repository_lock(repository):
                        logger.info(
                            "Successfully broke lock for local repository",
                            repository_id=repository.id,
                        )
                    else:
                        logger.warning(
                            "Failed to break lock for local repository",
                            repository_id=repository.id,
                        )
                        job.error_message += "\n" + json.dumps(
                            {"key": "backend.errors.service.warningFailedBreakLock"}
                        )
                else:
                    # For remote repos, don't auto-break lock (remote process may still be running)
                    logger.warning(
                        "Orphaned check job for remote repository - manual lock break may be needed",
                        repository_id=repository.id,
                    )
                    job.error_message += "\n" + json.dumps(
                        {
                            "key": "backend.errors.service.warningRemoteProcessMayBeRunning"
                        }
                    )

            backup_match_filter = BackupJob.repository_id == job.repository_id
            if job.repository_path:
                backup_match_filter = or_(
                    backup_match_filter,
                    and_(
                        BackupJob.repository_id.is_(None),
                        BackupJob.repository == job.repository_path,
                    ),
                )

            affected_backup_jobs = (
                db.query(BackupJob)
                .filter(
                    BackupJob.maintenance_status == "running_check",
                    backup_match_filter,
                )
                .all()
            )

            for backup_job in affected_backup_jobs:
                _mark_backup_maintenance_failed(backup_job, "running_check", now)
                logger.info(
                    "Marked backup maintenance state as failed after orphaned check",
                    backup_job_id=backup_job.id,
                    check_job_id=job.id,
                    repository=backup_job.repository,
                )
        else:
            # Process is still alive! This is unexpected
            logger.warning(
                "Check job marked as running and process is still alive",
                job_id=job.id,
                pid=job.process_pid,
            )

    # Process restore check jobs
    for job in running_restore_check_jobs:
        if not is_process_alive(job.process_pid, job.process_start_time):
            job.status = "failed"
            job.error_message = CONTAINER_RESTARTED_DURING_OPERATION
            job.completed_at = now
            logger.info(
                "Orphaned restore check job detected",
                job_id=job.id,
                repository_id=job.repository_id,
                pid=job.process_pid,
            )
        else:
            logger.warning(
                "Restore check job marked as running and process is still alive",
                job_id=job.id,
                pid=job.process_pid,
            )

    # Process prune jobs
    for job in running_prune_jobs:
        job.status = "failed"
        job.error_message = CONTAINER_RESTARTED_DURING_OPERATION
        job.completed_at = now

        logger.info(
            "Orphaned prune job detected",
            job_id=job.id,
            repository_id=job.repository_id,
        )

        affected_backup_jobs = (
            db.query(BackupJob)
            .filter(
                BackupJob.repository == job.repository_path,
                BackupJob.maintenance_status == "running_prune",
            )
            .all()
        )

        for backup_job in affected_backup_jobs:
            backup_job.maintenance_status = "prune_failed"
            logger.info(
                "Marked backup maintenance state as failed after orphaned prune",
                backup_job_id=backup_job.id,
                prune_job_id=job.id,
                repository=backup_job.repository,
            )

    # Process compact jobs
    for job in running_compact_jobs:
        if not is_process_alive(job.process_pid, job.process_start_time):
            # Process is dead! Mark job as failed
            job.status = "failed"
            job.error_message = CONTAINER_RESTARTED_DURING_OPERATION
            job.completed_at = now

            logger.info(
                "Orphaned compact job detected",
                job_id=job.id,
                repository_id=job.repository_id,
                pid=job.process_pid,
            )

            # Get repository to determine if we should auto-break lock
            repository = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )

            if repository:
                if not _is_remote_repository(repository, db):
                    # For local repos, we can safely break the lock
                    logger.info(
                        "Attempting to break lock for local repository",
                        repository_id=repository.id,
                    )
                    if break_repository_lock(repository):
                        logger.info(
                            "Successfully broke lock for local repository",
                            repository_id=repository.id,
                        )
                    else:
                        logger.warning(
                            "Failed to break lock for local repository",
                            repository_id=repository.id,
                        )
                        job.error_message += "\n" + json.dumps(
                            {"key": "backend.errors.service.warningFailedBreakLock"}
                        )
                else:
                    # For remote repos, don't auto-break lock
                    logger.warning(
                        "Orphaned compact job for remote repository - manual lock break may be needed",
                        repository_id=repository.id,
                    )
                    job.error_message += "\n" + json.dumps(
                        {
                            "key": "backend.errors.service.warningRemoteProcessMayBeRunning"
                        }
                    )

            affected_backup_jobs = (
                db.query(BackupJob)
                .filter(
                    BackupJob.repository == job.repository_path,
                    BackupJob.maintenance_status == "running_compact",
                )
                .all()
            )

            for backup_job in affected_backup_jobs:
                backup_job.maintenance_status = "compact_failed"
                logger.info(
                    "Marked backup maintenance state as failed after orphaned compact",
                    backup_job_id=backup_job.id,
                    compact_job_id=job.id,
                    repository=backup_job.repository,
                )
        else:
            # Process is still alive! This is unexpected
            logger.warning(
                "Compact job marked as running and process is still alive",
                job_id=job.id,
                pid=job.process_pid,
            )

    normalized_plan_runs = _normalize_interrupted_backup_plan_runs(
        db, now, active_backup_plan_runs
    )
    if normalized_plan_runs:
        logger.info(
            "Cleaned up interrupted backup plan runs",
            count=normalized_plan_runs,
        )

    # Commit all changes
    db.commit()

    logger.info("Orphaned job cleanup completed")


def cleanup_orphaned_mounts():
    """
    Cleanup stale FUSE mounts on container startup

    This function detects and cleans up orphaned SSHFS and Borg mounts
    that may have been left behind from container restarts or crashes.

    Should be called during application startup.
    """
    logger.info("Checking for orphaned mounts...")

    try:
        managed_mount_base = Path(settings.data_dir) / "mounts"

        result = subprocess.run(["mount"], capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            logger.warning("Failed to list mounts", returncode=result.returncode)
            return

        orphaned_count = 0

        for line in result.stdout.split("\n"):
            parts = line.split()
            if len(parts) < 3 or "on" not in parts:
                continue

            try:
                on_index = parts.index("on")
                if on_index + 1 >= len(parts):
                    continue
                mount_point = parts[on_index + 1]
            except (ValueError, IndexError):
                continue

            is_temp_mount = (
                "sshfs_mount_" in mount_point or "borg_backup_root_" in mount_point
            )
            is_managed_mount = False
            try:
                is_managed_mount = (
                    Path(mount_point)
                    .resolve()
                    .is_relative_to(managed_mount_base.resolve())
                )
            except Exception:
                pass

            if not is_temp_mount and not is_managed_mount:
                continue

            logger.info("Found orphaned mount", mount_point=mount_point)
            orphaned_count += 1

            try:
                cleanup_result = subprocess.run(
                    ["fusermount", "-uz", mount_point],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if cleanup_result.returncode == 0:
                    logger.info(
                        "Successfully unmounted orphaned mount",
                        mount_point=mount_point,
                    )
                else:
                    logger.warning(
                        "Failed to unmount orphaned mount",
                        mount_point=mount_point,
                        stderr=cleanup_result.stderr,
                    )
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Timeout unmounting orphaned mount",
                    mount_point=mount_point,
                )
            except FileNotFoundError:
                try:
                    cleanup_result = subprocess.run(
                        ["umount", "-f", mount_point],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if cleanup_result.returncode == 0:
                        logger.info(
                            "Successfully unmounted orphaned mount (umount)",
                            mount_point=mount_point,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to unmount with umount",
                        mount_point=mount_point,
                        error=str(e),
                    )
            except Exception as e:
                logger.error(
                    "Error unmounting orphaned mount",
                    mount_point=mount_point,
                    error=str(e),
                )

        if managed_mount_base.exists():
            for child in managed_mount_base.iterdir():
                if not child.is_dir():
                    continue
                try:
                    if any(child.iterdir()):
                        continue
                    child.rmdir()
                    logger.debug(
                        "Removed orphaned managed mount directory",
                        mount_point=str(child),
                    )
                except Exception as e:
                    logger.debug(
                        "Could not remove managed mount directory",
                        mount_point=str(child),
                        error=str(e),
                    )

        if orphaned_count > 0:
            logger.info(
                "Orphaned mount cleanup completed", cleaned_up_count=orphaned_count
            )
        else:
            logger.info("No orphaned mounts found")

    except subprocess.TimeoutExpired:
        logger.error("Timeout while listing mounts")
    except Exception as e:
        logger.error("Failed orphan mount cleanup", error=str(e))
