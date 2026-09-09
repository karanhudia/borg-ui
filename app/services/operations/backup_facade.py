"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
backup-job attribute surface, and the one place every backup is created.

`backup_service`, `remote_backup_service`, the backup routes, the agent
transport, the scheduler and the plan runner drive a backup through a fixed
set of attributes. Phase 8 moves the row to `operations` without rewriting
them: `resolve_backup_job()` hands them this facade for new work and the real
`BackupJob` for an id written before this phase.

Translations, all in one place:
- `status`: the legacy word `pending` is the operations word `queued`.
- `execution_mode`: the legacy word `local` is the spec 6.1 word `server`.
- `progress` (an int) and `progress_percent` are both
  `operations.progress_percent`.
- `logs`, which the services assign once at the end, is the operation's log
  file (spec 6.1); the marker text "Logs saved to: ..." the local service
  writes when it kept its own file is dropped, since the row already names
  the file.
- `repository` is the path of `repository_id`, or `params["repository"]`
  for the one legacy case with no repository (an unknown path submitted to
  the manual start route, recorded and failed at once).
- `backup_plan_id` is read through `backup_plan_run_id`.

Deleted in phase 9 with the legacy table.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.models import (
    BackupJob,
    BackupPlanRun,
    Operation,
    OperationBackupDetails,
    Repository,
)
from app.services.operations.details import backup_details
from app.services.operations.vocab import TERMINAL_STATUSES
from app.utils.backup_maintenance import RUNNING_BACKUP_MAINTENANCE_FAILURES

CANCELLED_BY_USER = json.dumps({"key": "backend.errors.backup.cancelledByUser"})
CANCELLED_PROCESS_NOT_FOUND = json.dumps(
    {"key": "backend.errors.backup.cancelledByUserProcessNotFound"}
)
CANCEL_MESSAGES = (CANCELLED_BY_USER, CANCELLED_PROCESS_NOT_FOUND)

# A backup whose `borg create` succeeded and whose row still ended `failed`
# because a post-backup hook failed. The archive exists, so the executor
# enqueues the index chain itself (Appendix B, phase 6 precedent for a
# failure that changed the repository).
POST_CREATE_FAILURE_KEYS = frozenset(
    {
        "backend.errors.service.postBackupHooksFailed",
        "backend.errors.service.backupWarningPostHooksFailed",
    }
)

# `params` keys handed to `backup_service.execute_backup` by name.
SERVICE_PARAMS = (
    "archive_name",
    "skip_hooks",
    "source_directories",
    "source_ssh_connection_id",
    "source_locations",
    "exclude_patterns_override",
    "compression_override",
    "custom_flags_override",
    "upload_ratelimit_kib",
)
# `params` keys handed to `queue_agent_backup_job`, mapped to its names.
AGENT_PARAMS = {
    "archive_name": "archive_name",
    "source_directories": "source_directories",
    "source_locations": "source_locations",
    "exclude_patterns_override": "exclude_patterns",
    "compression_override": "compression",
    "custom_flags_override": "custom_flags",
    "upload_ratelimit_kib": "upload_ratelimit_kib",
}

# The same three words the legacy readers match on, kept in one place.
RUNNING_MAINTENANCE_WORDS = tuple(RUNNING_BACKUP_MAINTENANCE_FAILURES)

_LEGACY_TO_OPERATION_MODE = {"local": "server"}
_OPERATION_TO_LEGACY_MODE = {"server": "local", None: "local"}

# Columns that live on the details row and need no translation.
# `current_file` is not here: it mirrors into `progress_message`.
_DETAIL_FIELDS = tuple(
    column.name
    for column in OperationBackupDetails.__table__.columns
    if column.name not in ("operation_id", "current_file")
)


class BackupJobFacade:
    """One `Operation` presented as a legacy backup job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "details", backup_details(db, operation))

    def __setattr__(self, name: str, value) -> None:
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "details"), name)
        raise AttributeError(f"backup operations carry no {name!r}")

    # -- identity ----------------------------------------------------------

    @property
    def id(self) -> int:
        return self.operation.id

    @property
    def kind(self) -> str:
        return self.operation.kind

    @property
    def repository_id(self) -> Optional[int]:
        return self.operation.repository_id

    @property
    def repository(self) -> Optional[str]:
        if self.operation.repository_id is None:
            return (self.operation.params or {}).get("repository")
        repository = self._db.get(Repository, self.operation.repository_id)
        return repository.path if repository is not None else None

    @property
    def scheduled_job_id(self) -> Optional[int]:
        return self.operation.scheduled_job_id

    @property
    def backup_plan_run_id(self) -> Optional[int]:
        return self.operation.backup_plan_run_id

    @property
    def backup_plan_id(self) -> Optional[int]:
        if self.operation.backup_plan_run_id is None:
            return None
        run = self._db.get(BackupPlanRun, self.operation.backup_plan_run_id)
        return run.backup_plan_id if run is not None else None

    @property
    def triggered_by(self) -> str:
        if self.operation.backup_plan_run_id:
            return "backup_plan"
        return "schedule" if self.operation.scheduled_job_id else "manual"

    @property
    def created_at(self):
        return self.operation.created_at

    # -- lifecycle ---------------------------------------------------------

    @property
    def status(self) -> str:
        return "pending" if self.operation.status == "queued" else self.operation.status

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = "queued" if value == "pending" else value

    @property
    def started_at(self):
        return self.operation.started_at

    @started_at.setter
    def started_at(self, value) -> None:
        self.operation.started_at = value

    @property
    def completed_at(self):
        return self.operation.completed_at

    @completed_at.setter
    def completed_at(self, value) -> None:
        self.operation.completed_at = value

    @property
    def error_message(self):
        return self.operation.error_message

    @error_message.setter
    def error_message(self, value) -> None:
        self.operation.error_message = value

    @property
    def execution_mode(self) -> str:
        mode = self.operation.execution_mode
        return _OPERATION_TO_LEGACY_MODE.get(mode, mode)

    @execution_mode.setter
    def execution_mode(self, value) -> None:
        self.operation.execution_mode = _LEGACY_TO_OPERATION_MODE.get(value, value)

    # -- progress ----------------------------------------------------------

    @property
    def progress(self) -> int:
        return int(self.operation.progress_percent or 0)

    @progress.setter
    def progress(self, value) -> None:
        self.operation.progress_percent = float(value or 0)

    @property
    def progress_percent(self) -> float:
        return float(self.operation.progress_percent or 0.0)

    @progress_percent.setter
    def progress_percent(self, value) -> None:
        self.operation.progress_percent = float(value or 0.0)

    @property
    def current_file(self) -> Optional[str]:
        return self.details.current_file

    @current_file.setter
    def current_file(self, value) -> None:
        self.details.current_file = value
        self.operation.progress_message = value or None

    # -- logs --------------------------------------------------------------

    @property
    def log_file_path(self):
        return self.operation.log_file_path

    @log_file_path.setter
    def log_file_path(self, value) -> None:
        self.operation.log_file_path = value

    @property
    def logs(self) -> str:
        path = self.operation.log_file_path
        if not path:
            return ""
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return ""

    @logs.setter
    def logs(self, value) -> None:
        from app.services.operations.runner import operation_log_path

        if value is None or str(value).startswith("Logs saved to:"):
            return
        path = (
            Path(self.operation.log_file_path)
            if self.operation.log_file_path
            else operation_log_path(self.operation.id)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(value), encoding="utf-8")
        self.operation.log_file_path = str(path)


def is_backup_operation(job: Any) -> bool:
    return isinstance(job, BackupJobFacade)


def resolve_backup_job(db: Session, job_id: int) -> Any:
    """The job a backup caller should drive for `job_id`. Operations win;
    ids from before this phase fall back to the legacy table."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "backup")
        .first()
    )
    if operation is not None:
        return BackupJobFacade(db, operation)
    return db.query(BackupJob).filter(BackupJob.id == job_id).first()


def refresh_backup_job(db: Session, job: Any) -> None:
    """`db.refresh(job)` for either shape: a facade refreshes its two rows."""
    if is_backup_operation(job):
        db.refresh(job.operation)
        db.refresh(job.details)
    else:
        db.refresh(job)


def admission_ignore_for(job: Any):
    from app.services.job_admission import ignore_active_job

    table = (
        Operation.__tablename__ if is_backup_operation(job) else BackupJob.__tablename__
    )
    return ignore_active_job(table, job.id)


def backup_job_link_columns(db: Session, job_id: Optional[int]) -> dict:
    """Which link column a row pointing at backup `job_id` should fill."""
    if job_id is None:
        return {"backup_job_id": None, "operation_id": None}
    if is_backup_operation(resolve_backup_job(db, job_id)):
        return {"backup_job_id": None, "operation_id": job_id}
    return {"backup_job_id": job_id, "operation_id": None}


def create_backup_operation(
    db: Session,
    repository: Optional[Repository],
    *,
    trigger: str,
    executor: str,
    params: Optional[dict] = None,
    user_id: Optional[int] = None,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    retry: Optional[dict] = None,
    repository_path: Optional[str] = None,
    commit: bool = True,
) -> BackupJobFacade:
    """The one creation site (spec 7.1). `executor` is `server` or `agent`
    and decides which path `run_backup` takes. `params` are the
    `execute_backup` keyword arguments the caller wants passed through
    (`SERVICE_PARAMS`); None values are dropped so a service default is not
    shadowed. `retry` holds the details row's retry columns. With
    `repository` None the caller passes the path it was given and is
    expected to fail the row itself before committing."""
    from app.services.backup_route_planner import apply_repository_route_to_backup_job
    from app.services.operations.enqueue import enqueue, wake_runner

    stored = {k: v for k, v in (params or {}).items() if v is not None}
    stored["executor"] = executor
    if repository is None:
        stored["repository"] = repository_path
    operation = enqueue(
        db,
        "backup",
        repository_id=repository.id if repository is not None else None,
        trigger=trigger,
        params=stored,
        triggered_by_user_id=user_id,
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
        commit=False,
    )
    job = BackupJobFacade(db, operation)
    job.source_ssh_connection_id = (
        repository.source_ssh_connection_id if repository is not None else None
    )
    if repository is not None and executor == "agent":
        job.execution_mode = "agent"
    elif repository is not None:
        apply_repository_route_to_backup_job(job, repository)
    else:
        job.execution_mode = "local"
    for name, value in (retry or {}).items():
        setattr(job, name, value)
    if commit:
        db.commit()
        db.refresh(operation)
        wake_runner()
    return job


async def wait_for_backup_operation(
    db: Session,
    operation_id: int,
    *,
    is_cancelled: Optional[Callable[[], bool]] = None,
    poll_interval_seconds: float = 0.5,
) -> str:
    """Block until the operation is terminal and return its legacy status
    word. A caller that learns it was cancelled (a plan run) asks the runner
    to cancel once; the executor's watcher does the rest (spec 7.7)."""
    from app.services.operations.runner import operation_runner

    cancel_sent = False
    while True:
        db.expire_all()
        operation = db.get(Operation, operation_id)
        if operation is None:
            return "failed"
        if operation.status in TERMINAL_STATUSES:
            return "pending" if operation.status == "queued" else operation.status
        if is_cancelled is not None and not cancel_sent and is_cancelled():
            cancel_sent = True
            await operation_runner.request_cancel(operation_id)
        await asyncio.sleep(poll_interval_seconds)


def backup_job_has_logs(
    db: Session, job: Any, *, log_save_policy: Optional[str] = None
) -> bool:
    """The `has_logs` answer for either shape, agent logs included."""
    from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
    from app.services.repository_executor import get_agent_job_for_backup

    policy = log_save_policy or get_log_save_policy(db)
    output_text: list = [job.logs, job.error_message]
    agent_job = None
    if job.execution_mode == "agent":
        agent_job = get_agent_job_for_backup(db, job)
        if agent_job:
            output_text.append(agent_job.error_message)
    if job_has_logs_by_policy(
        job, policy, output_text=output_text, file_path=job.log_file_path
    ):
        return True
    if policy == "failed_and_warnings" and agent_job is not None:
        from app.database.models import AgentJobLog

        messages = [
            log.message
            for log in db.query(AgentJobLog)
            .filter(AgentJobLog.agent_job_id == agent_job.id)
            .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
            .all()
        ]
        if messages:
            return job_has_logs_by_policy(
                job,
                policy,
                output_text=[*output_text, *messages],
                file_path=job.log_file_path,
            )
    return False


# -- union queries --------------------------------------------------------
#
# Each helper reads both tables and merges in Python. Both cuts rank by the
# same key the merge uses (the phase 7 lesson: cutting a source by id while
# merging by timestamp drops rows wherever the two orders disagree).


def _sort_key(attr: str):
    def key(job):
        value = getattr(job, attr, None) or getattr(job, "created_at", None)
        return (value or datetime.min, job.id)

    return key


def _operations_query(db: Session):
    return db.query(Operation).filter(Operation.kind == "backup")


def _facades(db: Session, operations: Iterable[Operation]) -> list:
    return [BackupJobFacade(db, op) for op in operations]


def list_backup_jobs(
    db: Session,
    limit: int,
    *,
    scheduled_only: bool = False,
    manual_only: bool = False,
    repository_path: Optional[str] = None,
) -> list:
    ops = _operations_query(db)
    legacy = db.query(BackupJob)
    if scheduled_only:
        ops = ops.filter(Operation.scheduled_job_id.isnot(None))
        legacy = legacy.filter(BackupJob.scheduled_job_id.isnot(None))
    elif manual_only:
        ops = ops.filter(
            Operation.scheduled_job_id.is_(None), Operation.backup_plan_run_id.is_(None)
        )
        legacy = legacy.filter(
            BackupJob.scheduled_job_id.is_(None), BackupJob.backup_plan_id.is_(None)
        )
    if repository_path:
        repository = (
            db.query(Repository).filter(Repository.path == repository_path).first()
        )
        ops = ops.filter(
            Operation.repository_id == (repository.id if repository else -1)
        )
        legacy = legacy.filter(BackupJob.repository == repository_path)
    jobs = _facades(
        db,
        ops.order_by(Operation.created_at.desc(), Operation.id.desc())
        .limit(limit)
        .all(),
    ) + list(
        legacy.order_by(BackupJob.created_at.desc(), BackupJob.id.desc())
        .limit(limit)
        .all()
    )
    jobs.sort(key=_sort_key("created_at"), reverse=True)
    return jobs[:limit]


def backup_jobs_started_since(
    db: Session, since, *, until=None, limit: Optional[int] = None
) -> list:
    ops = _operations_query(db).filter(Operation.started_at >= since)
    legacy = db.query(BackupJob).filter(BackupJob.started_at >= since)
    if until is not None:
        ops = ops.filter(Operation.started_at <= until)
        legacy = legacy.filter(BackupJob.started_at <= until)
    ops = ops.order_by(Operation.started_at.desc(), Operation.id.desc())
    legacy = legacy.order_by(BackupJob.started_at.desc(), BackupJob.id.desc())
    if limit is not None:
        ops = ops.limit(limit)
        legacy = legacy.limit(limit)
    jobs = _facades(db, ops.all()) + list(legacy.all())
    jobs.sort(key=_sort_key("started_at"), reverse=True)
    return jobs[:limit] if limit is not None else jobs


def latest_backup_job_for_repository(
    db: Session,
    repository: Repository,
    *,
    statuses: Optional[Iterable[str]] = None,
    order: str = "created",
    require_timestamps: bool = False,
) -> Any:
    ops = _operations_query(db).filter(Operation.repository_id == repository.id)
    legacy = db.query(BackupJob).filter(BackupJob.repository == repository.path)
    if statuses is not None:
        ops = ops.filter(Operation.status.in_(tuple(statuses)))
        legacy = legacy.filter(BackupJob.status.in_(tuple(statuses)))
    if order == "completed":
        if require_timestamps:
            ops = ops.filter(
                Operation.started_at.isnot(None), Operation.completed_at.isnot(None)
            )
            legacy = legacy.filter(
                BackupJob.started_at.isnot(None), BackupJob.completed_at.isnot(None)
            )
        ops = ops.order_by(Operation.completed_at.desc(), Operation.id.desc())
        legacy = legacy.order_by(BackupJob.completed_at.desc(), BackupJob.id.desc())
    else:
        ops = ops.order_by(Operation.created_at.desc(), Operation.id.desc())
        legacy = legacy.order_by(BackupJob.created_at.desc(), BackupJob.id.desc())
    candidates = _facades(db, ops.limit(1).all()) + list(legacy.limit(1).all())
    if not candidates:
        return None
    attr = "completed_at" if order == "completed" else "created_at"
    return max(candidates, key=_sort_key(attr))


def backup_jobs_for_archive_names(db: Session, repository: Repository, names) -> list:
    names = list(names)
    if not names:
        return []
    ops = (
        _operations_query(db)
        .join(
            OperationBackupDetails, OperationBackupDetails.operation_id == Operation.id
        )
        .filter(
            Operation.repository_id == repository.id,
            OperationBackupDetails.archive_name.in_(names),
        )
        .all()
    )
    filters = [BackupJob.archive_name.in_(names)]
    owners = []
    if getattr(repository, "id", None) is not None:
        owners.append(BackupJob.repository_id == repository.id)
    if getattr(repository, "path", None):
        owners.append(BackupJob.repository == repository.path)
    if owners:
        filters.append(or_(*owners))
    legacy = db.query(BackupJob).filter(*filters).all()
    jobs = _facades(db, ops) + list(legacy)
    jobs.sort(key=_sort_key("created_at"), reverse=True)
    return jobs


def _newest_per_group(db: Session, model, group_column, order_column, filters) -> list:
    """The newest row of each group, ranked in SQL. Only the winners are
    loaded, so a caller reading one row per repository does not materialize
    every backup ever taken (the window query the legacy path used)."""
    ranked = (
        db.query(
            model.id.label("row_id"),
            func.row_number()
            .over(
                partition_by=group_column,
                order_by=(order_column.desc(), model.id.desc()),
            )
            .label("rank"),
        )
        .filter(*filters)
        .subquery()
    )
    return (
        db.query(model)
        .join(ranked, model.id == ranked.c.row_id)
        .filter(ranked.c.rank == 1)
        .all()
    )


def latest_backup_jobs_by_repository(db: Session, *, running: bool = False) -> dict:
    """Newest (or newest running) backup per repository path, both tables."""
    op_filters = [Operation.kind == "backup", Operation.repository_id.isnot(None)]
    legacy_filters = [BackupJob.repository.isnot(None)]
    if running:
        op_filters.append(Operation.status == "running")
        legacy_filters.append(BackupJob.status == "running")
        op_order = func.coalesce(Operation.started_at, Operation.created_at)
        legacy_order = func.coalesce(BackupJob.started_at, BackupJob.created_at)
        attr = "started_at"
    else:
        op_order = Operation.created_at
        legacy_order = BackupJob.created_at
        attr = "created_at"
    # Operations group by repository_id and legacy rows by path; a repository
    # owns one path, so the two rankings meet on the same key below.
    candidates = _facades(
        db,
        _newest_per_group(db, Operation, Operation.repository_id, op_order, op_filters),
    ) + _newest_per_group(
        db, BackupJob, BackupJob.repository, legacy_order, legacy_filters
    )
    result: dict = {}
    for job in candidates:
        path = job.repository
        if not path:
            continue
        if path not in result or _sort_key(attr)(job) > _sort_key(attr)(result[path]):
            result[path] = job
    return result


def newest_backup_job(
    db: Session,
    *,
    running: bool = False,
    terminal: bool = False,
    terminal_statuses: Optional[Iterable[str]] = None,
) -> Any:
    """`terminal_statuses` narrows what counts as finished. A caller that
    reports the last backup outcome passes its own set, since the operations
    vocabulary counts `skipped` as terminal and a skipped run is not an
    outcome the legacy readers ever saw."""
    ops = _operations_query(db)
    legacy = db.query(BackupJob)
    attr = "created_at"
    if running:
        ops = ops.filter(Operation.status == "running")
        legacy = legacy.filter(BackupJob.status == "running")
        attr = "started_at"
    elif terminal:
        words = tuple(terminal_statuses or TERMINAL_STATUSES)
        ops = ops.filter(Operation.status.in_(words))
        legacy = legacy.filter(BackupJob.status.in_(words))
        attr = "completed_at"
    column = {
        "created_at": Operation.created_at,
        "started_at": Operation.started_at,
        "completed_at": Operation.completed_at,
    }[attr]
    legacy_column = getattr(BackupJob, attr)
    candidates = _facades(
        db, ops.order_by(column.desc(), Operation.id.desc()).limit(1).all()
    ) + list(legacy.order_by(legacy_column.desc(), BackupJob.id.desc()).limit(1).all())
    return max(candidates, key=_sort_key(attr)) if candidates else None


def backup_jobs_in_maintenance(db: Session) -> list:
    ops = (
        _operations_query(db)
        .join(
            OperationBackupDetails, OperationBackupDetails.operation_id == Operation.id
        )
        .filter(
            OperationBackupDetails.maintenance_status.in_(RUNNING_MAINTENANCE_WORDS)
        )
        .all()
    )
    legacy = (
        db.query(BackupJob)
        .filter(BackupJob.maintenance_status.in_(RUNNING_MAINTENANCE_WORDS))
        .all()
    )
    return _facades(db, ops) + list(legacy)
