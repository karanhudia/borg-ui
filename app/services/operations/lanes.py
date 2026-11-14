"""Per-repository lanes and global limits (spec sections 7.2 and 7.3)."""

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.database.models import (
    BackupPlanRunRepository,
    Operation,
    OperationBackupDetails,
    Repository,
    SystemSettings,
)
from app.services.agent_presence import backups_waiting_for_offline_agent
from app.services.operations.vocab import (
    INDEX_KINDS,
    KINDS,
    STAGE_FOR_KIND,
    is_exclusive,
)

_EXCLUSIVE_KINDS = tuple(k for k, spec in KINDS.items() if spec.exclusive)
# The index kinds that share the repository lane: listing, merge and stats.
# `history_index` is exclusive and holds the lane itself. Sorted, so the
# `IN (...)` literal is the same text in every process. Public: `/queue`
# names the running ones so the board does not keep its own copy of the
# set and drift from it when a kind is added.
SHARED_INDEX_KINDS = tuple(sorted(k for k in INDEX_KINDS if not KINDS[k].exclusive))

_DEFAULTS = {
    "max_concurrent_backups": 1,
    "max_concurrent_scheduled_backups": 2,
    "max_concurrent_scheduled_checks": 4,
    "max_concurrent_maintenance": None,
    "maintenance_counts_toward_backup_limit": False,
    "index_workers": 2,
    "paused_stages": [],
    "bypass_lock_on_list": False,
}


def _setting(settings: Optional[SystemSettings], name: str):
    value = getattr(settings, name, None) if settings is not None else None
    return _DEFAULTS[name] if value is None else value


# Kinds the job admission classes as repository writes: their agent and
# server jobs are refused with 409 while one of them runs, so a listing
# started under bypass_lock would fail instead of reading past a lock.
_WRITE_MAINTENANCE_KINDS = ("prune", "compact", "delete_archive", "wipe")
_MAINTENANCE_BACKUP_STATUSES = ("running_prune", "running_compact")


def write_maintenance_running(db: Session, repository_id: int) -> bool:
    """True while prune, compact, delete or wipe is queued or running on
    the repository, as an operation or as a backup in its maintenance phase
    (`maintenance_status`, the scheduler's post-backup prune and compact).
    Unlike a running backup, these are not something a listing can bypass:
    admission refuses the listing outright."""
    if (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == repository_id,
            Operation.status.in_(("queued", "running")),
            Operation.kind.in_(_WRITE_MAINTENANCE_KINDS),
        )
        .first()
    ):
        return True
    return (
        db.query(OperationBackupDetails.operation_id)
        .join(Operation, Operation.id == OperationBackupDetails.operation_id)
        .filter(
            Operation.repository_id == repository_id,
            OperationBackupDetails.maintenance_status.in_(_MAINTENANCE_BACKUP_STATUSES),
        )
        .first()
    ) is not None


def running_exclusive_operation(
    db: Session, repository_id: int, *, exclude_id: Optional[int] = None
) -> bool:
    q = db.query(Operation.id).filter(
        Operation.repository_id == repository_id,
        Operation.status == "running",
        Operation.kind.in_(_EXCLUSIVE_KINDS),
    )
    if exclude_id is not None:
        q = q.filter(Operation.id != exclude_id)
    return q.first() is not None


def lane_free(
    db: Session, repository_id: int, *, exclude_id: Optional[int] = None
) -> bool:
    return not running_exclusive_operation(db, repository_id, exclude_id=exclude_id)


def running_index_operation(db: Session, repository_id: int) -> bool:
    """True while a listing, merge or stats of the repository is running.

    No two of those overlap on one repository (spec 7.2): two chains of one
    run (the backup's follow-ups and the prune's) otherwise start their
    stats side by side, and on an agent's repository a listing started next
    to the stats' `rinfo` dies with rc 2, since Borg 1 holds the cache lock
    during `info` and `list` and the agent's calls are not serialised the
    way the server's own are (`run_serialized_repository_command`, scope
    `metadata`). A running `history_index` is not counted: it is exclusive
    and holds the lane, which the bypass setting may cross so an hours-long
    index does not hold the hourly listing; the server's metadata scope
    keeps its `borg diff` and the listing apart. On an agent's repository
    the diff runs as an agent job and the agent's listing does not take
    that scope, so with the bypass on the two can run side by side there.

    A row a dead task left `running` would hold the repository for good;
    the runner requeues such rows at every tick (as it does at startup),
    so the answer here is the state the runner is actually in."""
    return (
        db.query(Operation.id)
        .filter(
            Operation.status == "running",
            Operation.kind.in_(SHARED_INDEX_KINDS),
            Operation.repository_id == repository_id,
        )
        .first()
        is not None
    )


def running_count(
    db: Session,
    *,
    kind: Optional[str] = None,
    kinds: Optional[Iterable[str]] = None,
    trigger: Optional[str] = None,
    triggers: Optional[Iterable[str]] = None,
    category: Optional[str] = None,
) -> int:
    q = db.query(Operation.id).filter(Operation.status == "running")
    if kind is not None:
        q = q.filter(Operation.kind == kind)
    if kinds is not None:
        q = q.filter(Operation.kind.in_(tuple(kinds)))
    if trigger is not None:
        q = q.filter(Operation.trigger == trigger)
    if triggers is not None:
        q = q.filter(Operation.trigger.in_(tuple(triggers)))
    if category is not None:
        q = q.filter(Operation.category == category)
    return q.count()


# The maintenance `max_concurrent_maintenance` caps and
# `maintenance_counts_toward_backup_limit` puts in the backup slots. A prune
# preview (trigger `preview`) removes nothing and is not counted.
MAINTENANCE_SLOT_KINDS = ("prune", "compact", "check")


def _is_slot_maintenance(op: Operation) -> bool:
    return op.kind in MAINTENANCE_SLOT_KINDS and op.trigger != "preview"


def running_maintenance_count(db: Session, *, outside_plan_runs: bool = False) -> int:
    q = db.query(Operation.id).filter(
        Operation.status == "running",
        Operation.kind.in_(MAINTENANCE_SLOT_KINDS),
        Operation.trigger != "preview",
    )
    if outside_plan_runs:
        q = q.filter(Operation.backup_plan_run_id.is_(None))
    return q.count()


def _plan_backups_in_maintenance(db: Session, triggers: Iterable[str]) -> int:
    """Finished plan backups whose repository step is still open: the plan
    runs its post-backup prune, compact and checks inline in that window,
    so the step, not the backup, says when the repository is let go. This
    also covers the moment between the backup ending and its prune
    starting, which a count of running prunes alone would miss."""
    return (
        db.query(Operation.id)
        .join(
            BackupPlanRunRepository,
            BackupPlanRunRepository.backup_operation_id == Operation.id,
        )
        .filter(
            Operation.kind == "backup",
            Operation.status.notin_(("queued", "running")),
            Operation.trigger.in_(tuple(triggers)),
            BackupPlanRunRepository.status == "running",
        )
        .count()
    )


def running_backup_count(
    db: Session, *, triggers: Iterable[str], include_maintenance: bool = False
) -> int:
    """Running backups that hold a backup slot. One that waits for an agent
    that is away does not (#1331): its work runs on the agent, and until the
    agent is back it does nothing but wait, so it must not hold up the
    backups of every other machine.

    With `include_maintenance` a plan backup keeps its slot through its
    post-backup steps, and any other running prune, compact or check takes
    a slot in every pool: it loads the same storage whichever pool it
    would belong to."""
    triggers = tuple(triggers)
    ids = [
        operation_id
        for (operation_id,) in db.query(Operation.id).filter(
            Operation.status == "running",
            Operation.kind == "backup",
            Operation.trigger.in_(triggers),
        )
    ]
    count = len(ids) - len(backups_waiting_for_offline_agent(db, ids))
    if include_maintenance:
        count += _plan_backups_in_maintenance(db, triggers)
        count += running_maintenance_count(db, outside_plan_runs=True)
    return count


_NON_SCHEDULED_BACKUP_TRIGGERS = (
    "manual",
    "plan",
    "import",
    "retry",
    "followup",
    "reconcile",
)


def _maintenance_slot_available(
    db: Session, op: Operation, settings: Optional[SystemSettings]
) -> bool:
    cap = _setting(settings, "max_concurrent_maintenance")
    if cap and running_maintenance_count(db) >= cap:
        return False
    if op.kind == "check" and op.trigger == "schedule":
        limit = _setting(settings, "max_concurrent_scheduled_checks")
        if running_count(db, kind="check", trigger="schedule") >= limit:
            return False
    if not _setting(settings, "maintenance_counts_toward_backup_limit"):
        return True
    if op.trigger == "schedule":
        limit = _setting(settings, "max_concurrent_scheduled_backups")
        triggers = ("schedule",)
    else:
        limit = _setting(settings, "max_concurrent_backups")
        triggers = _NON_SCHEDULED_BACKUP_TRIGGERS
    return running_backup_count(db, triggers=triggers, include_maintenance=True) < limit


def global_slot_available(
    db: Session, op: Operation, settings: Optional[SystemSettings]
) -> bool:
    if op.kind == "backup":
        shared = bool(_setting(settings, "maintenance_counts_toward_backup_limit"))
        if op.trigger == "schedule":
            limit = _setting(settings, "max_concurrent_scheduled_backups")
            return (
                running_backup_count(
                    db, triggers=("schedule",), include_maintenance=shared
                )
                < limit
            )
        limit = _setting(settings, "max_concurrent_backups")
        return (
            running_backup_count(
                db, triggers=_NON_SCHEDULED_BACKUP_TRIGGERS, include_maintenance=shared
            )
            < limit
        )
    if _is_slot_maintenance(op):
        return _maintenance_slot_available(db, op, settings)
    if op.kind in INDEX_KINDS:
        return running_count(db, kinds=INDEX_KINDS) < _setting(
            settings, "index_workers"
        )
    return True


def can_start(db: Session, op: Operation, settings: Optional[SystemSettings]) -> bool:
    paused = _setting(settings, "paused_stages") or []
    if STAGE_FOR_KIND.get(op.kind) in paused and op.trigger in (
        "followup",
        "reconcile",
    ):
        return False
    if not global_slot_available(db, op, settings):
        return False
    if op.repository_id is None:
        return True
    if op.kind in INDEX_KINDS and running_index_operation(db, op.repository_id):
        # No second index operation next to a running listing, merge or
        # stats of the repository, bypass or not: that setting reads past
        # a backup's lock, not past another index job.
        return False
    if is_exclusive(op.kind):
        return lane_free(db, op.repository_id, exclude_id=op.id)
    if op.kind in INDEX_KINDS:
        # Admission refuses a listing while prune, compact, delete or wipe
        # is pending or running, whatever the lane says (a pending job holds
        # no lane yet) and whatever bypass_lock says (that reads past a
        # running backup's lock, not past admission). Checked before the
        # lane and bypass decision: the backup follow-up chain otherwise
        # fails with 409 against the plan's own post-backup prune.
        if write_maintenance_running(db, op.repository_id):
            return False
        if lane_free(db, op.repository_id, exclude_id=op.id):
            return True
        repository = db.get(Repository, op.repository_id)
        repo_bypass = bool(repository.bypass_lock) if repository is not None else False
        return repo_bypass or bool(_setting(settings, "bypass_lock_on_list"))
    return True
