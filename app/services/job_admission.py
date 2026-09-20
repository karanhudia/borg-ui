"""DB-backed admission checks for repository job dispatch."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import structlog
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.models import (
    AgentJob,
    Operation,
    Repository,
    SystemSettings,
)

logger = structlog.get_logger()

OPERATION_BACKUP = "backup"
OPERATION_CHECK = "check"
OPERATION_RESTORE = "restore"
OPERATION_RESTORE_CHECK = "restore_check"
OPERATION_COMPACT = "compact"
OPERATION_PRUNE = "prune"
OPERATION_DELETE_ARCHIVE = "delete_archive"
OPERATION_REPOSITORY_WIPE = "repository_wipe"
OPERATION_REPOSITORY_INIT = "repository.init"
OPERATION_REPOSITORY_INFO = "repository.info"
OPERATION_REPOSITORY_LIST_ARCHIVES = "repository.list_archives"
OPERATION_REPOSITORY_LIST_ARCHIVE_CONTENTS = "repository.list_archive_contents"
OPERATION_REPOSITORY_EXTRACT_ARCHIVE_FILE = "repository.extract_archive_file"
OPERATION_REPOSITORY_EXPORT_ARCHIVE_TAR = "repository.export_archive_tar"
OPERATION_REPOSITORY_DIFF = "repository.diff"
OPERATION_BREAK_LOCK = "break_lock"
OPERATION_DISK_USAGE = "repository.disk_usage"
OPERATION_STORAGE_USAGE = "repository.storage_usage"
OPERATION_RCLONE_SYNC = "repository.rclone_sync"
# Sentinel for an active repository agent job whose kind we don't recognize.
# Classed WRITE so admission fails closed -- an unknown job might hold a borg
# lock, and break_lock must never run alongside it.
OPERATION_UNKNOWN_REPOSITORY = "repository.unknown"

OPERATION_CLASS_REPOSITORY_WRITE = "repository_write"
OPERATION_CLASS_REPOSITORY_READ = "repository_read"
# Observation: reads metadata ABOUT the repository without opening it, so it
# holds no borg lock and conflicts with nothing. Distinct from
# repository_read, which does open the repository and must therefore still
# yield to a write.
OPERATION_CLASS_REPOSITORY_OBSERVE = "repository_observe"

DEFAULT_MANUAL_BACKUP_LIMIT = 1
DEFAULT_SCHEDULED_BACKUP_LIMIT = 2

ACTIVE_MAINTENANCE_STATUSES = {"pending", "running"}
ACTIVE_AGENT_STATUSES = {"queued", "claimed", "cancel_requested", "running"}
ACTIVE_OPERATION_STATUSES = {"queued", "running"}

# Every kind admission watches, mapped to the admission operation it is
# recorded as.
MIGRATED_OPERATION_KINDS = {
    "check": OPERATION_CHECK,
    "restore_check": OPERATION_RESTORE_CHECK,
    "compact": OPERATION_COMPACT,
    "prune": OPERATION_PRUNE,
    "delete_archive": OPERATION_DELETE_ARCHIVE,
    "backup": OPERATION_BACKUP,
    "wipe": OPERATION_REPOSITORY_WIPE,
}

REPOSITORY_OPERATION_ACTIVE_KEY = "backend.errors.jobs.repositoryOperationActive"
MANUAL_BACKUP_LIMIT_KEY = "backend.errors.backup.concurrentLimitReached"

WRITE_OPERATIONS = {
    OPERATION_BACKUP,
    OPERATION_COMPACT,
    OPERATION_PRUNE,
    OPERATION_DELETE_ARCHIVE,
    OPERATION_REPOSITORY_WIPE,
    OPERATION_REPOSITORY_INIT,
    # break-lock forcibly removes the repo lock, so it must not run alongside
    # ANY active borg process on the repo (reads hold locks too) -- classing it
    # WRITE makes it conflict with all active work. A genuinely stale lock (no
    # active work) still passes admission and is recovered.
    OPERATION_BREAK_LOCK,
    OPERATION_UNKNOWN_REPOSITORY,
}
READ_OPERATIONS = {
    OPERATION_CHECK,
    OPERATION_RESTORE,
    OPERATION_RESTORE_CHECK,
    OPERATION_REPOSITORY_INFO,
    OPERATION_REPOSITORY_LIST_ARCHIVES,
    OPERATION_REPOSITORY_LIST_ARCHIVE_CONTENTS,
    OPERATION_REPOSITORY_EXTRACT_ARCHIVE_FILE,
    OPERATION_REPOSITORY_EXPORT_ARCHIVE_TAR,
    # The change listing between two archives (or one archive's full
    # listing) for the history index: opens the repository read-only. It
    # can run for hours on a large archive, so it is not transient read
    # work: a write that arrives meanwhile is refused, not waited out.
    OPERATION_REPOSITORY_DIFF,
    # rclone reads the repository and writes only to the remote, so it
    # cannot corrupt local state the way a write operation can.
    OPERATION_RCLONE_SYNC,
}

# du stats the repository directory; it never opens the repository, so it
# neither takes a borg lock nor needs to wait for one.
OBSERVE_OPERATIONS = {
    OPERATION_DISK_USAGE,
    # The chunk-index read takes no lock (lock=False) and the store tools
    # never open the repository.
    OPERATION_STORAGE_USAGE,
}

AGENT_JOB_KIND_OPERATIONS = {
    "repository.check": OPERATION_CHECK,
    "repository.prune": OPERATION_PRUNE,
    "repository.compact": OPERATION_COMPACT,
    "repository.init": OPERATION_REPOSITORY_INIT,
    "repository.info": OPERATION_REPOSITORY_INFO,
    "repository.rinfo": OPERATION_REPOSITORY_INFO,
    "repository.archive_info": OPERATION_REPOSITORY_INFO,
    "repository.list_archives": OPERATION_REPOSITORY_LIST_ARCHIVES,
    "repository.delete_archive": OPERATION_DELETE_ARCHIVE,
    "repository.break_lock": OPERATION_BREAK_LOCK,
    "repository.list_archive_contents": OPERATION_REPOSITORY_LIST_ARCHIVE_CONTENTS,
    "repository.extract_archive_file": OPERATION_REPOSITORY_EXTRACT_ARCHIVE_FILE,
    "repository.export_archive_tar": OPERATION_REPOSITORY_EXPORT_ARCHIVE_TAR,
    "repository.diff": OPERATION_REPOSITORY_DIFF,
    "repository.restore": OPERATION_RESTORE,
    "repository.disk_usage": OPERATION_DISK_USAGE,
    "repository.storage_usage": OPERATION_STORAGE_USAGE,
    "repository.rclone_sync": OPERATION_RCLONE_SYNC,
}


@dataclass(frozen=True)
class ActiveRepositoryWork:
    resource_type: str
    resource_id: int
    operation: str
    operation_class: str
    job_table: str
    job_id: int
    status: str


@dataclass(frozen=True)
class IgnoreActiveJob:
    job_table: str
    job_id: int


def operation_class_for(operation: str) -> str:
    if operation in WRITE_OPERATIONS:
        return OPERATION_CLASS_REPOSITORY_WRITE
    if operation in READ_OPERATIONS:
        return OPERATION_CLASS_REPOSITORY_READ
    if operation in OBSERVE_OPERATIONS:
        return OPERATION_CLASS_REPOSITORY_OBSERVE
    raise ValueError(f"Unknown repository operation: {operation}")


def operation_for_agent_job_kind(job_kind: str) -> str:
    try:
        return AGENT_JOB_KIND_OPERATIONS[job_kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported agent repository operation: {job_kind}") from exc


def ignore_active_job(
    job_table: Optional[str], job_id: Optional[int]
) -> Optional[IgnoreActiveJob]:
    if not job_table or job_id is None:
        return None
    return IgnoreActiveJob(job_table=job_table, job_id=job_id)


def _is_ignored(work: ActiveRepositoryWork, ignore: Optional[IgnoreActiveJob]) -> bool:
    return bool(
        ignore and work.job_table == ignore.job_table and work.job_id == ignore.job_id
    )


def _dialect_name(db: Session) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""


def _lock_repository_scope(db: Session, repository: Repository) -> None:
    if repository.id is None:
        return
    if _dialect_name(db) == "sqlite":
        db.execute(
            text("UPDATE repositories SET id = id WHERE id = :repository_id"),
            {"repository_id": repository.id},
        )
        return
    db.query(Repository).filter(
        Repository.id == repository.id
    ).with_for_update().first()


def lock_backup_capacity_scope(db: Session) -> None:
    """Serialize capacity checks with later job inserts in the transaction."""
    dialect_name = _dialect_name(db)
    if dialect_name == "sqlite":
        db.execute(
            text(
                "UPDATE system_settings SET id = id "
                "WHERE id = (SELECT id FROM system_settings ORDER BY id ASC LIMIT 1)"
            )
        )
        return
    if dialect_name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": 276116})
        return
    db.query(SystemSettings).order_by(SystemSettings.id.asc()).with_for_update().first()


def _active_work(
    repository: Repository,
    operation: str,
    job_table: str,
    job: Any,
    *,
    status: Optional[str] = None,
) -> ActiveRepositoryWork:
    return ActiveRepositoryWork(
        resource_type="repository",
        resource_id=int(repository.id),
        operation=operation,
        operation_class=operation_class_for(operation),
        job_table=job_table,
        job_id=int(job.id),
        status=str(job.status if status is None else status),
    )


def list_active_repository_work(
    db: Session,
    repository: Repository,
    *,
    ignore: Optional[IgnoreActiveJob] = None,
) -> list[ActiveRepositoryWork]:
    """Return persisted active work for a repository grouped by operation class."""
    active: list[ActiveRepositoryWork] = []

    # Every kind lives in `operations`. Admission must see them, or break_lock
    # and wipe would run alongside a check or a prune that is holding the borg
    # lock.
    from app.services.operations.job_facade import legacy_status

    for op in (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind.in_(tuple(MIGRATED_OPERATION_KINDS)),
            Operation.status.in_(ACTIVE_OPERATION_STATUSES),
        )
        .all()
    ):
        active.append(
            _active_work(
                repository,
                MIGRATED_OPERATION_KINDS[op.kind],
                Operation.__tablename__,
                op,
                status=legacy_status(op.status),
            )
        )

    agent_jobs = (
        db.query(AgentJob)
        .filter(
            AgentJob.job_type == "repository",
            AgentJob.status.in_(ACTIVE_AGENT_STATUSES),
        )
        .all()
    )
    for job in agent_jobs:
        payload = job.payload if isinstance(job.payload, dict) else {}
        repository_payload = payload.get("repository")
        if not isinstance(repository_payload, dict):
            continue
        payload_repo_id = repository_payload.get("id")
        payload_repo_path = repository_payload.get("path")
        if payload_repo_id != repository.id and payload_repo_path != repository.path:
            continue
        job_kind = payload.get("job_kind")
        try:
            operation = operation_for_agent_job_kind(str(job_kind))
        except ValueError:
            # Fail closed: an unrecognized active repository job might still hold
            # a borg lock, so count it as (write-class) conflicting work rather
            # than ignoring it -- otherwise break_lock could run alongside it.
            operation = OPERATION_UNKNOWN_REPOSITORY
        active.append(_active_work(repository, operation, AgentJob.__tablename__, job))

    return [work for work in active if not _is_ignored(work, ignore)]


def _conflict_detail(
    key: str,
    repository: Repository,
    requested_operation: str,
    active: ActiveRepositoryWork,
) -> dict[str, Any]:
    return {
        "key": key,
        "params": {
            "repository_id": repository.id,
            "repository": repository.path,
            "requested_operation": requested_operation,
            "active_operation": active.operation,
            "active_operation_class": active.operation_class,
            "active_job_table": active.job_table,
            "active_job_id": active.job_id,
            "active_status": active.status,
        },
    }


def ensure_repository_admission(
    db: Session,
    repository: Repository,
    operation: str,
    *,
    duplicate_error_key: Optional[str] = None,
    ignore: Optional[IgnoreActiveJob] = None,
) -> None:
    """Reject duplicate or conflicting active work before a job is queued."""
    _lock_repository_scope(db, repository)
    requested_class = operation_class_for(operation)
    active_work = list_active_repository_work(db, repository, ignore=ignore)

    for active in active_work:
        if active.operation == operation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_conflict_detail(
                    duplicate_error_key or REPOSITORY_OPERATION_ACTIVE_KEY,
                    repository,
                    operation,
                    active,
                ),
            )

    for active in active_work:
        # An observation neither takes a lock nor waits for one, so it is
        # skipped from both sides: it never blocks a backup, and it can start
        # while anything else is running.
        if OPERATION_CLASS_REPOSITORY_OBSERVE in (
            requested_class,
            active.operation_class,
        ):
            continue
        conflicts = requested_class == OPERATION_CLASS_REPOSITORY_WRITE or (
            requested_class == OPERATION_CLASS_REPOSITORY_READ
            and active.operation_class == OPERATION_CLASS_REPOSITORY_WRITE
        )
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_conflict_detail(
                    REPOSITORY_OPERATION_ACTIVE_KEY,
                    repository,
                    operation,
                    active,
                ),
            )


# Read work that is over in seconds: the listing and the repository info
# the agent runs for the index follow-up chain and the stats refresh. A
# write refused because of one can be asked for again shortly. Every other
# read-class operation (a check, a restore, an archive listing someone
# browses, a mirror) runs for minutes to hours, and a queued one cannot
# even start while the caller's own exclusive row is running, so waiting
# for it is pointless.
TRANSIENT_READ_OPERATIONS = frozenset(
    {
        OPERATION_REPOSITORY_INFO,
        OPERATION_REPOSITORY_LIST_ARCHIVES,
    }
)
# How long a write may wait for transient read work. The work a plan's
# prune collides with is one listing plus a bounded batch of archive infos
# (`index_archive_info_per_run`), each a few seconds; transient work still
# active after this is an agent that stopped answering, which the agent job
# reaper handles. Deliberately not the borg list/info timeouts: operators
# raise those for very large repositories, and a plan run must not stall
# behind one repository for that long.
TRANSIENT_READ_WAIT_SECONDS = 180.0


def refused_by_read_work(exc: BaseException, *, transient_only: bool = True) -> bool:
    """True for the admission's 409 whose blocker is read work.

    With `transient_only` (the default) only read work that is over in
    seconds counts; anything else (a conflicting write, a duplicate of the
    same operation, a long-running read, another error) is not worth a
    wait and must reach the caller unchanged. Without it any read-class
    blocker counts, `repository.diff` included: a caller whose only other
    answer is to fail outright prefers a bounded wait to a refusal.
    """
    if getattr(exc, "status_code", None) != status.HTTP_409_CONFLICT:
        return False
    detail = getattr(exc, "detail", None)
    if (
        not isinstance(detail, dict)
        or detail.get("key") != REPOSITORY_OPERATION_ACTIVE_KEY
    ):
        return False
    params = detail.get("params")
    if not isinstance(params, dict):
        return False
    active = params.get("active_operation")
    if active == params.get("requested_operation"):
        # the same operation is already active: a duplicate, not a lock wait
        return False
    if params.get("active_operation_class") != OPERATION_CLASS_REPOSITORY_READ:
        return False
    return not transient_only or active in TRANSIENT_READ_OPERATIONS


# What `wait_for_read_work_to_clear` came back with.
READ_WORK_CLEARED = "cleared"  # no read work left
READ_WORK_BLOCKED = "blocked"  # read work that will not clear on its own
READ_WORK_UNCLAIMED = "unclaimed"  # only never-claimed jobs left, past the grace
READ_WORK_CANCELLED = "cancelled"  # the caller's run was cancelled
READ_WORK_TIMEOUT = "timeout"  # transient work still active at the deadline
# A queued agent job is usually claimed within a second of its dispatch.
# One the agent never picks up (it dropped between queue and dispatch) is
# not reaped: the agent job reaper watches claimed and running jobs only.
# Past this grace a wait that sees nothing but queued read work gives up.
UNCLAIMED_READ_WORK_GRACE_SECONDS = 30.0


async def wait_for_read_work_to_clear(
    db: Session,
    repository: Repository,
    *,
    timeout_seconds: float,
    transient_only: bool = True,
    poll_interval_seconds: float = 1.0,
    is_cancelled: Optional[Callable[[], bool]] = None,
    unclaimed_grace_seconds: float = UNCLAIMED_READ_WORK_GRACE_SECONDS,
) -> str:
    """Wait until no transient read work is active on the repository.

    Returns `READ_WORK_CLEARED` once the repository is free of read work.
    With `transient_only` (the default) returns at once with
    `READ_WORK_BLOCKED` when read work that will not clear on its own is
    active (any read-class operation outside
    `TRANSIENT_READ_OPERATIONS`: a check, a restore, a mirror) and with
    `READ_WORK_CANCELLED` when `is_cancelled` says so; with
    `READ_WORK_UNCLAIMED` when the only read work left is queued jobs no
    agent has claimed for `unclaimed_grace_seconds`, counted from the
    moment that became the case for those jobs; and with
    `READ_WORK_TIMEOUT` when the deadline passes with transient work still
    active. Without `transient_only` no read work is treated as blocking:
    every read-class operation is waited out until the deadline. Write work is not looked at: a write refused by a write is not
    this function's case.

    The session's transaction is ended before every poll and before
    returning: the refused admission that brings a caller here left the
    repository row locked, and neither the polls nor the caller's pause
    afterwards may hold that lock or pin a pooled connection idle in a
    transaction. `is_cancelled` is asked once per poll; a caller whose
    check is expensive hands in a throttled one.
    """
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    # The grace runs from the moment nothing but queued jobs is left, for
    # that set of jobs: a listing that ran for a while and then queued a
    # new job must not use up the new job's grace, and a claim in between
    # starts it over.
    unclaimed_since: Optional[float] = None
    unclaimed_jobs: frozenset[tuple[str, int]] = frozenset()
    while True:
        db.rollback()
        read_work = [
            work
            for work in list_active_repository_work(db, repository)
            if work.operation_class == OPERATION_CLASS_REPOSITORY_READ
        ]
        db.rollback()
        if not read_work:
            return READ_WORK_CLEARED
        if transient_only and any(
            work.operation not in TRANSIENT_READ_OPERATIONS for work in read_work
        ):
            return READ_WORK_BLOCKED
        now = time.monotonic()
        if all(work.status == "queued" for work in read_work):
            jobs = frozenset((work.job_table, work.job_id) for work in read_work)
            if unclaimed_since is None or jobs != unclaimed_jobs:
                unclaimed_since, unclaimed_jobs = now, jobs
            elif now - unclaimed_since >= unclaimed_grace_seconds:
                return READ_WORK_UNCLAIMED
        else:
            unclaimed_since, unclaimed_jobs = None, frozenset()
        if is_cancelled is not None and is_cancelled():
            return READ_WORK_CANCELLED
        remaining = deadline - now
        if remaining <= 0:
            return READ_WORK_TIMEOUT
        await asyncio.sleep(min(poll_interval_seconds, remaining))


# How long a backup plan's repository run may wait for read work on its
# repository before giving up and failing that repository, as it did
# before this wait existed. Sits just past the agent job reaper's window
# (15 minutes of silence) plus one pass of its loop, so read work whose
# agent died is cleared by the reaper and the backup still runs. Work
# still active after that is a live long read -- a `repository.diff` over
# a large archive -- and a plan run must not stall behind one repository
# indefinitely.
PLAN_BACKUP_READ_WAIT_SECONDS = 17 * 60.0

READ_WORK_ADMITTED = "admitted"  # the operation passed admission


async def admit_repository_with_read_work_wait(
    db: Session,
    repository: Repository,
    operation: str,
    *,
    timeout_seconds: float,
    transient_only: bool = True,
    is_cancelled: Optional[Callable[[], bool]] = None,
    # Each poll costs a query for the active work and, for a plan, one
    # more for the run's cancel flag. Read work this wait is for lasts
    # seconds at least, so polling every second buys nothing.
    poll_interval_seconds: float = 5.0,
    retry_pause_seconds: float = 1.0,
) -> str:
    """Admit `operation`, waiting out read work instead of failing on it.

    Returns `READ_WORK_ADMITTED` once admission passes and
    `READ_WORK_CANCELLED` when `is_cancelled` says the caller's run is
    over. A refusal for anything but read work propagates unchanged, and
    so does the latest refusal once the budget is spent or the wait
    reports work that will not clear -- the caller then fails exactly as
    it did before.

    This is the admission-only counterpart of the wait a plan's prune and
    compact already do before queueing their agent job; it exists for the
    callers that only need the check, such as a plan's backup.
    """
    log = logger.bind(repository_id=repository.id, operation=operation)
    deadline: Optional[float] = None
    attempts = 0
    while True:
        if is_cancelled is not None and is_cancelled():
            return READ_WORK_CANCELLED
        attempts += 1
        try:
            ensure_repository_admission(db, repository, operation)
        except HTTPException as exc:
            if not refused_by_read_work(exc, transient_only=transient_only):
                raise
            refusal = exc
        else:
            return READ_WORK_ADMITTED
        params = (
            refusal.detail.get("params") if isinstance(refusal.detail, dict) else None
        )
        active_operation = (params or {}).get("active_operation")
        if deadline is None:
            deadline = time.monotonic() + max(0.0, timeout_seconds)
            log.info(
                "Waiting for read work on the repository before admission",
                active_operation=active_operation,
                timeout_seconds=timeout_seconds,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.warning(
                "Gave up waiting for read work on the repository",
                reason="budget spent",
                attempts=attempts,
                active_operation=active_operation,
                timeout_seconds=timeout_seconds,
            )
            raise refusal
        # The wait ends this session's transaction around each poll, which
        # releases the repository row lock the refused admission took.
        outcome = await wait_for_read_work_to_clear(
            db,
            repository,
            timeout_seconds=remaining,
            transient_only=transient_only,
            poll_interval_seconds=poll_interval_seconds,
            is_cancelled=is_cancelled,
        )
        if outcome == READ_WORK_CANCELLED:
            return READ_WORK_CANCELLED
        if outcome != READ_WORK_CLEARED:
            log.warning(
                "Gave up waiting for read work on the repository",
                reason=outcome,
                attempts=attempts,
                active_operation=active_operation,
            )
            raise refusal
        # A short pause before asking again: the index follow-up chain
        # queues one job after another, and a retry that lands in the gap
        # between two of them must not spin against admission.
        await asyncio.sleep(
            min(retry_pause_seconds, max(0.0, deadline - time.monotonic()))
        )


def count_active_manual_backup_jobs(db: Session) -> int:
    return (
        db.query(Operation)
        .filter(
            Operation.kind == "backup",
            Operation.status.in_(tuple(ACTIVE_OPERATION_STATUSES)),
            Operation.scheduled_job_id.is_(None),
            Operation.backup_plan_run_id.is_(None),
        )
        .count()
    )


def get_manual_backup_limit(db: Session) -> int:
    settings = db.query(SystemSettings).first()
    if settings and settings.max_concurrent_backups is not None:
        return settings.max_concurrent_backups
    return DEFAULT_MANUAL_BACKUP_LIMIT


def ensure_manual_backup_capacity(db: Session) -> None:
    lock_backup_capacity_scope(db)
    limit = get_manual_backup_limit(db)
    active_count = count_active_manual_backup_jobs(db)
    if limit <= 0 or active_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "key": MANUAL_BACKUP_LIMIT_KEY,
                "params": {"limit": limit, "active": active_count},
            },
        )


def count_active_scheduled_backup_jobs(db: Session) -> int:
    return (
        db.query(Operation)
        .filter(
            Operation.kind == "backup",
            Operation.status.in_(tuple(ACTIVE_OPERATION_STATUSES)),
            Operation.scheduled_job_id.isnot(None),
        )
        .count()
    )


def get_scheduled_backup_limit(db: Session) -> int:
    settings = db.query(SystemSettings).first()
    if settings and settings.max_concurrent_scheduled_backups is not None:
        return settings.max_concurrent_scheduled_backups
    return DEFAULT_SCHEDULED_BACKUP_LIMIT
