"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
backup-job attribute surface, and the one place every backup is created.

`backup_service`, `remote_backup_service`, the backup routes, the agent
transport, the scheduler and the plan runner drive a backup through a fixed
set of attributes. Phase 8 moves the row to `operations` without rewriting
them: `resolve_backup_job()` hands them this facade.

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
  for the one case with no repository (an unknown path submitted to the
  manual start route, recorded and failed at once).
- `backup_plan_id` is read through `backup_plan_run_id`.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import case, func, nullslast, or_, tuple_
from sqlalchemy.orm import Session

from app.database.models import (
    Archive,
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

# The same three words every maintenance reader matches on, in one place.
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
    """True for every job `resolve_backup_job` returns, since phase 9 left
    one table. Callers keep asking, so the question keeps an answer."""
    return isinstance(job, BackupJobFacade)


def resolve_backup_job(db: Session, job_id: int) -> Optional[BackupJobFacade]:
    """The job a backup caller should drive for `job_id`, or None when no
    backup operation has the id."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "backup")
        .first()
    )
    if operation is None:
        return None
    return BackupJobFacade(db, operation)


def refresh_backup_job(db: Session, job: Any) -> None:
    """`db.refresh(job)`: a facade refreshes its two rows."""
    db.refresh(job.operation)
    db.refresh(job.details)


def admission_ignore_for(job: Any):
    from app.services.job_admission import ignore_active_job

    return ignore_active_job(Operation.__tablename__, job.id)


def backup_job_link_columns(db: Session, job_id: Optional[int]) -> dict:
    """Which link column a row pointing at backup `job_id` should fill."""
    return {"operation_id": job_id}


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
    """The `has_logs` answer for one backup, agent logs included. One backup
    can afford its transcript: the file is read even where the agent's log
    lines carry no marker, so a marker the database's `LIKE` does not see
    (SQLite reads a text up to its first NUL byte) still counts, as the
    routes that serve the text expect."""
    return backup_jobs_have_logs(
        db, [job], log_save_policy=log_save_policy, lines_decide=False
    )[job.id]


def backup_jobs_have_logs(
    db: Session,
    jobs: list,
    *,
    log_save_policy: Optional[str] = None,
    lines_decide: bool = True,
) -> dict:
    """`has_logs` per job id for a list of backups. The agent jobs and, where
    the policy's answer depends on them, their log lines are asked about once
    for the list, not once per backup.

    The transcript is the last thing consulted: the policy decides on the
    status, the exit code and the error messages first, and only a backup
    those leave undecided (a clean completion under `failed_and_warnings`)
    has its text searched for a marker. Two of the three policies never
    look at text, so listing backups under them opens no file.

    With `lines_decide`, an agent backup whose log lines carry no marker
    is answered by them and its file is left unread (a list's choice);
    without it, the file is read after the lines (`backup_job_has_logs`)."""
    from app.database.models import AgentJob, AgentJobLog
    from app.services.log_policy import (
        WARNING_MARKERS,
        get_log_save_policy,
        job_has_logs_by_policy,
        job_is_pending,
    )
    from app.services.repository_executor import BACKUP_AGENT_JOB_TYPE

    policy = log_save_policy or get_log_save_policy(db)
    agent_ids = [job.id for job in jobs if job.execution_mode == "agent"]
    # The newest transport job of each backup, as `get_agent_job_for_backup`
    # picks it, without the payload and result columns.
    agent_jobs: dict = {}
    for start in range(0, len(agent_ids), IN_CHUNK):
        for row in (
            db.query(AgentJob.id, AgentJob.operation_id, AgentJob.error_message)
            .filter(
                AgentJob.operation_id.in_(agent_ids[start : start + IN_CHUNK]),
                AgentJob.job_type == BACKUP_AGENT_JOB_TYPE,
            )
            .order_by(AgentJob.id.asc())
        ):
            agent_jobs[row.operation_id] = row

    answers: dict = {}
    undecided: dict = {}
    for job in jobs:
        output_text: list = [job.error_message]
        agent_job = agent_jobs.get(job.id)
        if agent_job is not None:
            output_text.append(agent_job.error_message)
        answers[job.id] = job_has_logs_by_policy(
            job, policy, output_text=output_text, file_path=job.log_file_path
        )
        if not answers[job.id] and not job_is_pending(job):
            undecided[job.id] = (job, output_text, agent_job)
    if policy != "failed_and_warnings" or not undecided:
        return answers

    # What can still change the answer is a marker in the agent's log lines.
    # The database picks one such line per job and the policy decides on it,
    # so a status it refuses whatever the text says (a requeued backup that
    # is pending again) stays refused, and the lines of every listed backup
    # are not loaded to be searched here. An agent backup's log file is
    # written from these lines when it completes, so lines that carry no
    # marker answer for the file too; only a backup whose lines are gone
    # falls through to its file below.
    marked = or_(
        *(func.lower(AgentJobLog.message).contains(m) for m in WARNING_MARKERS)
    )
    by_agent_job = {
        agent_job.id: job_id
        for job_id, (_, _, agent_job) in undecided.items()
        if agent_job is not None
    }
    agent_job_ids = sorted(by_agent_job)
    for start in range(0, len(agent_job_ids), IN_CHUNK):
        for agent_job_id, line in (
            db.query(
                AgentJobLog.agent_job_id,
                func.min(case((marked, AgentJobLog.message))),
            )
            .filter(
                AgentJobLog.agent_job_id.in_(agent_job_ids[start : start + IN_CHUNK])
            )
            .group_by(AgentJobLog.agent_job_id)
        ):
            job_id = by_agent_job[agent_job_id]
            if line is None:
                if lines_decide:
                    undecided.pop(job_id)
                continue
            job, output_text, _ = undecided.pop(job_id)
            answers[job.id] = job_has_logs_by_policy(
                job,
                policy,
                output_text=[*output_text, line],
                file_path=job.log_file_path,
            )
    for job, output_text, _ in undecided.values():
        if not job.log_file_path:
            continue
        answers[job.id] = job_has_logs_by_policy(
            job,
            policy,
            output_text=[*output_text, job.logs],
            file_path=job.log_file_path,
        )
    return answers


# -- readers --------------------------------------------------------------
#
# One table since phase 9, so each helper is a single query whose ordering and
# limit the route contracts still depend on.


def _sort_key(attr: str):
    def key(job):
        value = getattr(job, attr, None) or getattr(job, "created_at", None)
        return (value or datetime.min, job.id)

    return key


def _operations_query(db: Session):
    return db.query(Operation).filter(Operation.kind == "backup")


# Rows per `IN (...)` when a reader loads by id: SQLite's default variable
# limit is 999, the chunk stays well under it.
IN_CHUNK = 500


def _preload_details(db: Session, operations: list) -> list:
    """Load the details rows of `operations` in a few `IN` queries so that
    the `db.get` each facade constructor performs is an identity-map hit for
    every operation that has a details row, rather than one round trip per
    row (a list of thousands of backups used to cost thousands of
    statements). An operation without one still costs the constructor its
    lookup and the insert. The rows are returned because the identity map
    only holds them weakly: the caller keeps the list alive until the
    facades hold the rows themselves."""
    ids = [op.id for op in operations]
    rows = []
    for start in range(0, len(ids), IN_CHUNK):
        chunk = ids[start : start + IN_CHUNK]
        rows.extend(
            db.query(OperationBackupDetails)
            .filter(OperationBackupDetails.operation_id.in_(chunk))
            .all()
        )
    return rows


def _facades(db: Session, operations: Iterable[Operation]) -> list:
    operations = list(operations)
    preloaded = _preload_details(db, operations) if len(operations) > 1 else []
    facades = [BackupJobFacade(db, op) for op in operations]
    del preloaded
    return facades


def list_backup_jobs(
    db: Session,
    limit: int,
    *,
    scheduled_only: bool = False,
    manual_only: bool = False,
    repository_path: Optional[str] = None,
) -> list:
    ops = _operations_query(db)
    if scheduled_only:
        ops = ops.filter(Operation.scheduled_job_id.isnot(None))
    elif manual_only:
        ops = ops.filter(
            Operation.scheduled_job_id.is_(None), Operation.backup_plan_run_id.is_(None)
        )
    if repository_path:
        repository = (
            db.query(Repository).filter(Repository.path == repository_path).first()
        )
        ops = ops.filter(
            Operation.repository_id == (repository.id if repository else -1)
        )
    return _facades(
        db,
        ops.order_by(Operation.created_at.desc(), Operation.id.desc())
        .limit(limit)
        .all(),
    )


def backup_jobs_started_since(
    db: Session, since, *, until=None, limit: Optional[int] = None
) -> list:
    ops = _operations_query(db).filter(Operation.started_at >= since)
    if until is not None:
        ops = ops.filter(Operation.started_at <= until)
    ops = ops.order_by(Operation.started_at.desc(), Operation.id.desc())
    if limit is not None:
        ops = ops.limit(limit)
    return _facades(db, ops.all())


def recent_backup_jobs(db: Session, limit: int) -> list:
    """The newest backups by start time, with queued rows kept.

    A queued backup has no `started_at`; it sorts last here rather than being
    filtered out.
    """
    return _facades(
        db,
        _operations_query(db)
        .order_by(nullslast(Operation.started_at.desc()), Operation.id.desc())
        .limit(limit)
        .all(),
    )


def latest_backup_job_for_repository(
    db: Session,
    repository: Repository,
    *,
    statuses: Optional[Iterable[str]] = None,
    order: str = "created",
    require_timestamps: bool = False,
) -> Any:
    ops = _operations_query(db).filter(Operation.repository_id == repository.id)
    if statuses is not None:
        ops = ops.filter(Operation.status.in_(tuple(statuses)))
    if order == "completed":
        if require_timestamps:
            ops = ops.filter(
                Operation.started_at.isnot(None), Operation.completed_at.isnot(None)
            )
        ops = ops.order_by(Operation.completed_at.desc(), Operation.id.desc())
    else:
        ops = ops.order_by(Operation.created_at.desc(), Operation.id.desc())
    candidates = _facades(db, ops.limit(1).all())
    return candidates[0] if candidates else None


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
    jobs = _facades(db, ops)
    jobs.sort(key=_sort_key("created_at"), reverse=True)
    return jobs


def _nearest_start(rows, anchor):
    """The row whose `start` is nearest `anchor`; a tie goes to the newest id
    so the answer is stable across calls."""
    if anchor is None:
        return rows[0]
    return min(rows, key=lambda r: (abs(r.start - anchor), -r.id))


def link_archive_to_backup(db: Session, archive: Archive) -> None:
    """Record which backup made a newly listed archive (spec 6.4).

    Borg reports no operation id, so the match is by name: the completed
    backup in the repository with that archive name that no stored archive
    claims yet, nearest in start time when a Borg 2 series repeats the name.
    """
    claimed = db.query(Archive.backup_operation_id).filter(
        Archive.repository_id == archive.repository_id,
        Archive.backup_operation_id.isnot(None),
    )
    candidates = (
        db.query(Operation.id, Operation.started_at.label("start"))
        .join(
            OperationBackupDetails, OperationBackupDetails.operation_id == Operation.id
        )
        .filter(
            Operation.repository_id == archive.repository_id,
            Operation.kind == "backup",
            Operation.status.in_(("completed", "completed_with_warnings")),
            Operation.started_at.isnot(None),
            OperationBackupDetails.archive_name == archive.name,
            Operation.id.notin_(claimed),
        )
        .all()
    )
    if candidates:
        archive.backup_operation_id = _nearest_start(candidates, archive.start).id


def archive_borg_id_for(db: Session, job: "BackupJobFacade") -> Optional[str]:
    """The stored archive's borg id for a backup, or None if none is stored.

    The sync links each new archive to its backup; rows stored before that
    link existed fall back to the same-name row nearest the job's start.
    `Archive.name` is the full name for both Borg versions.
    """
    return archive_borg_ids_for(db, [job])[job.id]


def archive_borg_ids_for(db: Session, jobs: list) -> dict:
    """`archive_borg_id_for` per job id for a list of backups: one query on
    the repository index per chunk of backups, not one per listed job."""
    named = [job for job in jobs if job.archive_name and job.repository_id is not None]
    # Pairs, not a repository list and a name list: two independent `IN`s
    # would also match every other listed repository's archive of that name.
    pairs = sorted({(job.repository_id, job.archive_name) for job in named})
    stored: dict = {}
    for start in range(0, len(pairs), IN_CHUNK // 2):
        for row in (
            db.query(
                Archive.id,
                Archive.borg_id,
                Archive.start,
                Archive.backup_operation_id,
                Archive.repository_id,
                Archive.name,
            )
            .filter(
                tuple_(Archive.repository_id, Archive.name).in_(
                    pairs[start : start + IN_CHUNK // 2]
                )
            )
            .order_by(Archive.id.asc())
        ):
            stored.setdefault((row.repository_id, row.name), []).append(row)
    borg_ids: dict = {job.id: None for job in jobs}
    for job in named:
        rows = stored.get((job.repository_id, job.archive_name))
        if not rows:
            continue
        linked = [r for r in rows if r.backup_operation_id == job.id]
        borg_ids[job.id] = (
            linked[0] if linked else _nearest_start(rows, job.started_at)
        ).borg_id
    return borg_ids


def backup_facades(db: Session, operations: Iterable[Operation]) -> list:
    """Facades for backup operations a caller already holds, their details
    rows loaded once for the list."""
    return _facades(db, operations)


def newest_per_group(db: Session, model, group_column, order_column, filters) -> list:
    """The newest row of each group, ranked in SQL. Only the winners are
    loaded, so a caller reading one row per repository does not materialize
    every backup ever taken."""
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
    """Newest (or newest running) backup per repository path."""
    op_filters = [Operation.kind == "backup", Operation.repository_id.isnot(None)]
    if running:
        op_filters.append(Operation.status == "running")
        op_order = func.coalesce(Operation.started_at, Operation.created_at)
        attr = "started_at"
    else:
        op_order = Operation.created_at
        attr = "created_at"
    candidates = _facades(
        db,
        newest_per_group(db, Operation, Operation.repository_id, op_order, op_filters),
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
    outcome the routes ever reported."""
    ops = _operations_query(db)
    attr = "created_at"
    if running:
        ops = ops.filter(Operation.status == "running")
        attr = "started_at"
    elif terminal:
        words = tuple(terminal_statuses or TERMINAL_STATUSES)
        ops = ops.filter(Operation.status.in_(words))
        attr = "completed_at"
    column = {
        "created_at": Operation.created_at,
        "started_at": Operation.started_at,
        "completed_at": Operation.completed_at,
    }[attr]
    candidates = _facades(
        db, ops.order_by(column.desc(), Operation.id.desc()).limit(1).all()
    )
    return candidates[0] if candidates else None


def backup_jobs_in_maintenance(db: Session) -> list:
    return _facades(
        db,
        _operations_query(db)
        .join(
            OperationBackupDetails, OperationBackupDetails.operation_id == Operation.id
        )
        .filter(
            OperationBackupDetails.maintenance_status.in_(RUNNING_MAINTENANCE_WORDS)
        )
        .all(),
    )
