"""Per-repository lanes and global limits (spec sections 7.2 and 7.3)."""

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.database.models import (
    Operation,
    OperationBackupDetails,
    Repository,
    SystemSettings,
)
from app.services.operations.vocab import INDEX_KINDS, KINDS, is_exclusive

_EXCLUSIVE_KINDS = tuple(k for k, spec in KINDS.items() if spec.exclusive)
# The index kinds that share the repository lane: listing, merge and stats.
# `history_index` is exclusive and holds the lane itself. Sorted, so the
# `IN (...)` literal is the same text in every process.
_SHARED_INDEX_KINDS = tuple(sorted(k for k in INDEX_KINDS if not KINDS[k].exclusive))

_DEFAULTS = {
    "max_concurrent_backups": 1,
    "max_concurrent_scheduled_backups": 2,
    "max_concurrent_scheduled_checks": 4,
    "index_workers": 2,
    "background_paused": False,
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
    keeps its `borg diff` and the listing apart, and an agent's repository
    has no history stage.

    A row a dead task left `running` would hold the repository for good;
    the runner requeues such rows at every tick (as it does at startup),
    so the answer here is the state the runner is actually in."""
    return repository_id in repositories_with_running_index_work(
        db, repository_ids=(repository_id,)
    )


def repositories_with_running_index_work(
    db: Session, *, repository_ids: Optional[Iterable[int]] = None
) -> set[int]:
    """The repositories with a listing, merge or stats running, in one
    query; `repository_ids` narrows it. See `running_index_operation`."""
    q = db.query(Operation.repository_id).filter(
        Operation.status == "running",
        Operation.kind.in_(_SHARED_INDEX_KINDS),
        Operation.repository_id.isnot(None),
    )
    if repository_ids is not None:
        ids = tuple(repository_ids)
        if not ids:
            return set()
        q = q.filter(Operation.repository_id.in_(ids))
    return {row.repository_id for row in q.distinct()}


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


def global_slot_available(
    db: Session, op: Operation, settings: Optional[SystemSettings]
) -> bool:
    if op.kind == "backup":
        if op.trigger == "schedule":
            limit = _setting(settings, "max_concurrent_scheduled_backups")
            return running_count(db, kind="backup", trigger="schedule") < limit
        limit = _setting(settings, "max_concurrent_backups")
        non_scheduled = ("manual", "plan", "import", "retry", "followup", "reconcile")
        return running_count(db, kind="backup", triggers=non_scheduled) < limit
    if op.kind == "check" and op.trigger == "schedule":
        limit = _setting(settings, "max_concurrent_scheduled_checks")
        return running_count(db, kind="check", trigger="schedule") < limit
    if op.kind in INDEX_KINDS:
        return running_count(db, kinds=INDEX_KINDS) < _setting(
            settings, "index_workers"
        )
    return True


def can_start(db: Session, op: Operation, settings: Optional[SystemSettings]) -> bool:
    if _setting(settings, "background_paused") and op.trigger in (
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
