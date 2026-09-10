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
from sqlalchemy import func
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
    Operation,
    Repository,
)
from app.services.operations.backup_facade import backup_jobs_in_maintenance
from app.utils.backup_maintenance import (
    COMPLETED_BACKUP_STATUSES,
    MAINTENANCE_STATUS_KIND,
    RUNNING_BACKUP_MAINTENANCE_FAILURES,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
    resolve_repository_ssh_connection,
)

logger = structlog.get_logger()

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


def _has_running_check_child(db: Session, backup_job) -> bool:
    """True while a check operation is running on the backup's repository."""
    if backup_job.repository_id is None:
        return False
    return (
        db.query(Operation.id)
        .filter(
            Operation.kind == "check",
            Operation.status == "running",
            Operation.repository_id == backup_job.repository_id,
        )
        .first()
        is not None
    )


def _mark_backup_maintenance_failed(
    backup_job,
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


def _has_running_maintenance_child(
    db: Session, backup_job, maintenance_status: str
) -> bool:
    """True if a maintenance child operation for this repo is still running.

    The child operation is created `running` for both server-side and
    agent-delegated maintenance, so it is a reliable liveness signal. An agent
    maintenance job names no backup, so we correlate by repository (mirroring
    _has_running_check_child).
    """
    kind = MAINTENANCE_STATUS_KIND.get(maintenance_status)
    if kind is None or backup_job.repository_id is None:
        return False
    return (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == backup_job.repository_id,
            Operation.kind == kind,
            Operation.status == "running",
        )
        .first()
        is not None
    )


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
        # 2) age guard (a backup has no updated_at; completed_at is set when the
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


# An agent maintenance job carries no operation link on the agent job row, so a
# maintenance operation is correlated to its agent job via the payload's
# maintenance_job {kind, id}.
_ACTIVE_AGENT_STATUSES = ("queued", "claimed", "cancel_requested", "running")


def active_agent_maintenance_jobs(db: Session) -> set[tuple[str, int]]:
    """The `(kind, id)` of every maintenance operation a live agent job is
    carrying, read once so a reap pass can check many rows against it.
    `operations` is the only id space left, so the payload's `table` marker
    is not consulted: a payload written before the collapse names an id from
    a table that is gone, which cannot be mapped to the operation the copy
    became, and counting it as-is at worst keeps another row of the same kind
    alive for one pass rather than reaping a live one."""
    active = (
        db.query(AgentJob.payload)
        .filter(
            AgentJob.job_type == "repository",
            AgentJob.status.in_(_ACTIVE_AGENT_STATUSES),
        )
        .all()
    )
    refs: set[tuple[str, int]] = set()
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
        try:
            # The payload is JSON, so the id can arrive as a string; it has to
            # match `Operation.id` or a live operation reads as orphaned.
            refs.add((str(kind), int(job_id)))
        except (TypeError, ValueError):
            continue
    return refs


def has_active_agent_job_for(
    db: Session, maintenance_kind: str, maintenance_operation_id: int
) -> bool:
    """True if a live agent job is carrying this maintenance operation."""
    return (
        maintenance_kind,
        maintenance_operation_id,
    ) in active_agent_maintenance_jobs(db)


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
        if (kind, operation_id) in live:
            continue  # dispatched, the agent is on it
        # A guarded UPDATE: only a row that
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
            if has_active_agent_job_for(db, kind, operation_id):
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
    """Normalise what a restart leaves behind that the operations runner's
    own recovery (spec 7.6) does not cover: backup rows still in a running
    maintenance state, and backup plan runs left active."""
    logger.info("Checking for orphaned jobs...")

    now = datetime.utcnow()
    stale_backup_jobs = _mark_stale_backup_maintenance_failed(db, now)
    active_backup_plan_runs = (
        db.query(BackupPlanRun)
        .filter(BackupPlanRun.status.in_(ACTIVE_PLAN_RUN_STATUSES))
        .all()
    )
    logger.info(
        "Found interrupted work",
        stale_backup_maintenance_jobs=stale_backup_jobs,
        active_backup_plan_runs=len(active_backup_plan_runs),
    )

    if not stale_backup_jobs and not active_backup_plan_runs:
        logger.info("No orphaned jobs found")
        return

    normalized_plan_runs = _normalize_interrupted_backup_plan_runs(
        db, now, active_backup_plan_runs
    )
    if normalized_plan_runs:
        logger.info(
            "Cleaned up interrupted backup plan runs",
            count=normalized_plan_runs,
        )

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
