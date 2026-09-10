"""An `operations` row wearing the legacy maintenance-job attribute surface.

The five maintenance services (check, prune, compact, delete archive, restore
check) each take a job id and drive one row through a small set of attributes.
Phase 5 (spec section 13) moves the row from a per-kind table to `operations`
without rewriting those services: `resolve_maintenance_job()` hands them this
facade instead of the legacy model, and every attribute write lands on the
operation's own columns (spec 6.1). Kind-specific inputs live in
`operations.params`, since spec 6.2 gives these kinds no extension table.

Deleted in phase 9 with the legacy tables, at which point the services can
read `Operation` directly.
"""

from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database.models import (
    CheckJob,
    CompactJob,
    DeleteArchiveJob,
    Operation,
    PruneJob,
    Repository,
    RestoreCheckJob,
)
from app.services.operations.backup_facade import newest_per_group

MAINTENANCE_KINDS: tuple[str, ...] = (
    "check",
    "prune",
    "compact",
    "delete_archive",
    "restore_check",
)

LEGACY_MODELS: dict[str, Any] = {
    "check": CheckJob,
    "prune": PruneJob,
    "compact": CompactJob,
    "delete_archive": DeleteArchiveJob,
    "restore_check": RestoreCheckJob,
}

# The inputs each kind carries in `operations.params` (spec 6.2). A service
# reading anything outside its own tuple is a bug, so the facade raises
# rather than returning None and letting a wrong flag through silently.
PARAM_FIELDS: dict[str, tuple[str, ...]] = {
    "check": ("max_duration", "extra_flags", "scheduled_check"),
    "prune": (
        "keep_hourly",
        "keep_daily",
        "keep_weekly",
        "keep_monthly",
        "keep_quarterly",
        "keep_yearly",
        "keep_within",
        "dry_run",
        "scheduled_prune",
    ),
    "compact": ("scheduled_compact",),
    "delete_archive": ("archive_name",),
    "restore_check": (
        "archive_name",
        "probe_paths",
        "full_archive",
        "scheduled_restore_check",
    ),
}

# Params whose absence means False rather than None, so a service testing
# `if job.scheduled_check:` behaves as it does against the legacy column.
_BOOLEAN_PARAMS = frozenset(
    {
        "scheduled_check",
        "scheduled_prune",
        "scheduled_compact",
        "scheduled_restore_check",
        "full_archive",
        "dry_run",
    }
)

# The words that differ between the two vocabularies (spec 6.3). The restore
# check's `needs_backup` is `skipped` with that reason on an operation; the
# facade's status property carries the reason both ways.
_LEGACY_TO_OPERATION = {"pending": "queued", "needs_backup": "skipped"}
_OPERATION_TO_LEGACY = {"queued": "pending"}
NEEDS_BACKUP = "needs_backup"


def operation_status(status: str) -> str:
    """The operations word for a status a legacy service wrote."""
    return _LEGACY_TO_OPERATION.get(status, status)


def legacy_status(status: str) -> str:
    """The legacy word for an operations status, for readers still speaking
    the old vocabulary (the job status routes, the agent callbacks)."""
    return _OPERATION_TO_LEGACY.get(status, status)


class MaintenanceJobFacade:
    """One `Operation` presented as a legacy maintenance job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "_fields", PARAM_FIELDS.get(operation.kind, ()))

    def __setattr__(self, name: str, value) -> None:
        # A kind-specific input (e.g. restore_check writing back the archive
        # it resolved) lives in `operation.params`, not on this object, so a
        # plain `object.__setattr__` would silently drop it. Everything else
        # (status, progress, ...) is a real property below and goes through
        # the normal descriptor path via `object.__setattr__`.
        fields = object.__getattribute__(self, "_fields")
        if name in fields:
            operation = object.__getattribute__(self, "operation")
            params = dict(operation.params or {})
            params[name] = value
            operation.params = params
            return
        object.__setattr__(self, name, value)

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
    def repository_path(self) -> Optional[str]:
        params = self.operation.params or {}
        if params.get("repository_path"):
            return params["repository_path"]
        if self.operation.repository_id is None:
            return None
        repository = self._db.get(Repository, self.operation.repository_id)
        return repository.path if repository is not None else None

    @property
    def created_at(self):
        return self.operation.created_at

    # -- lifecycle ---------------------------------------------------------

    @property
    def status(self) -> str:
        if (
            self.operation.status == "skipped"
            and self.operation.skip_reason == NEEDS_BACKUP
        ):
            return NEEDS_BACKUP
        return legacy_status(self.operation.status)

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = operation_status(value)
        if value == NEEDS_BACKUP:
            self.operation.skip_reason = NEEDS_BACKUP

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
    def skip_reason(self):
        """Why a `skipped` operation did not run (spec 6.3); a legacy row has
        no such column, its `needs_backup` status carries the reason."""
        return self.operation.skip_reason

    @skip_reason.setter
    def skip_reason(self, value) -> None:
        self.operation.skip_reason = value

    # -- progress ----------------------------------------------------------

    @property
    def progress(self) -> int:
        return int(self.operation.progress_percent or 0)

    @progress.setter
    def progress(self, value) -> None:
        self.operation.progress_percent = float(value or 0)

    @property
    def progress_message(self):
        return self.operation.progress_message

    @progress_message.setter
    def progress_message(self, value) -> None:
        self.operation.progress_message = value

    # -- process ownership (spec 7.6 reads these on restart) ---------------

    @property
    def process_pid(self):
        return self.operation.process_pid

    @process_pid.setter
    def process_pid(self, value) -> None:
        self.operation.process_pid = value

    @property
    def process_start_time(self):
        return self.operation.process_start_time

    @process_start_time.setter
    def process_start_time(self, value) -> None:
        self.operation.process_start_time = value

    # -- logs --------------------------------------------------------------

    @property
    def log_file_path(self):
        return self.operation.log_file_path

    @log_file_path.setter
    def log_file_path(self, value) -> None:
        self.operation.log_file_path = value

    @property
    def logs(self) -> str:
        """The legacy `logs` column was a text mirror of the log file. The
        operation keeps only the file, so reads come from disk."""
        path = self.operation.log_file_path
        if not path:
            return ""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    @logs.setter
    def logs(self, value) -> None:
        """A service writes this as backwards-compatible text alongside
        `log_file_path`, a pattern from the legacy tables where the two are
        independent columns. Here `.logs` reads through the same file
        `log_file_path` points at, so a no-op once that file already has
        content: otherwise a service's post-write marker (e.g. "Logs saved
        to: X") clobbers the real captured output moments after it wrote
        it. Still creates the file for a service that never wrote one (an
        early failure with no log content at all), so that text has
        somewhere `logs`/`read_job_logs` can find it."""
        from pathlib import Path

        from app.services.operations.runner import operation_log_path

        path = self.operation.log_file_path
        if path and Path(path).exists():
            return
        text = value or ""
        if not path:
            resolved = operation_log_path(self.operation.id)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            path = str(resolved)
            self.operation.log_file_path = path
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            pass

    @property
    def has_logs(self) -> bool:
        return bool(self.logs)

    @has_logs.setter
    def has_logs(self, value) -> None:
        """Derived from the file. Accepted and dropped so a service that sets
        it alongside `logs` keeps working."""
        return None

    # -- summary -----------------------------------------------------------

    @property
    def stats(self):
        """Statistics the service recorded for this run (a Borg 2 compact's
        `--stats` output). Kept under `result["stats"]`, the kind-specific
        output summary of spec 6.1, next to whatever the executor adds."""
        result = self.operation.result
        return result.get("stats") if isinstance(result, dict) else None

    @stats.setter
    def stats(self, value) -> None:
        stored = self.operation.result
        result = dict(stored) if isinstance(stored, dict) else {}
        if value is None:
            result.pop("stats", None)
        else:
            result["stats"] = value
        self.operation.result = result or None

    # -- kind-specific inputs ---------------------------------------------

    def __getattr__(self, name: str):
        # Only reached when normal lookup fails, so every property above wins.
        fields = object.__getattribute__(self, "_fields")
        if name not in fields:
            raise AttributeError(
                f"{object.__getattribute__(self, 'operation').kind} operations "
                f"carry no {name!r}"
            )
        params = object.__getattribute__(self, "operation").params or {}
        if name in _BOOLEAN_PARAMS:
            return bool(params.get(name, False))
        return params.get(name)


def resolve_maintenance_job(db: Session, job_id: int, kind: str) -> Any:
    """The job a maintenance service should drive for `job_id`.

    Operations win, so new work runs on the new table. Ids that belong to a
    row written before this phase fall back to the legacy table, which keeps
    the job status routes and the agent callbacks working for history.
    """
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == kind)
        .first()
    )
    if operation is not None:
        return MaintenanceJobFacade(db, operation)
    model = LEGACY_MODELS.get(kind)
    if model is None:
        return None
    return db.query(model).filter(model.id == job_id).first()


def resolve_agent_maintenance_job(
    db: Session, payload: Any, *, kinds: Iterable[str] = MAINTENANCE_KINDS
) -> Any:
    """The maintenance job an agent job's payload names, or None; only for
    the `kinds` the caller handles.

    The payload's `operation.maintenance_job` carries `kind`, `id` and, for
    every job queued since the marker exists, `table`. The `operations` ids
    and the legacy ``*_jobs`` ids are separate sequences, so the table is
    what tells them apart. A payload without it predates the marker and may
    name either; the payload's repository decides (the row of the same
    repository, an operation first, and nothing when neither row is that
    repository's), and a payload without a repository takes the operation,
    as before.
    """
    if not isinstance(payload, dict):
        return None
    operation_payload = payload.get("operation")
    maintenance = (
        operation_payload.get("maintenance_job")
        if isinstance(operation_payload, dict)
        else None
    )
    if not isinstance(maintenance, dict):
        return None
    kind = str(maintenance.get("kind") or "")
    if kind not in MAINTENANCE_KINDS or kind not in set(kinds):
        return None
    try:
        job_id = int(maintenance.get("id"))
    except (TypeError, ValueError):
        return None
    if job_id <= 0:
        return None
    table = maintenance.get("table")
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == kind)
        .first()
    )
    if table == Operation.__tablename__:
        return MaintenanceJobFacade(db, operation) if operation is not None else None
    model = LEGACY_MODELS[kind]
    if table and table != model.__tablename__:
        return None
    legacy = db.query(model).filter(model.id == job_id).first()
    if table:
        return legacy
    repository = payload.get("repository")
    repository_id = repository.get("id") if isinstance(repository, dict) else None
    candidates = [
        candidate
        for candidate in (
            MaintenanceJobFacade(db, operation) if operation is not None else None,
            legacy,
        )
        if candidate is not None
    ]
    if repository_id is not None:
        # a row of another repository is never the one this job reports on
        matching = [c for c in candidates if c.repository_id == repository_id]
        return matching[0] if matching else None
    return candidates[0] if candidates else None


def refresh_job(db: Session, job: Any) -> None:
    """`db.refresh()` requires a mapped instance, which a facade is not: its
    mapped object is `.operation`. Callers hold either shape after
    `resolve_maintenance_job`, so route the refresh accordingly rather than
    let `Session.refresh` raise `UnmappedInstanceError` on a facade."""
    db.refresh(job.operation if isinstance(job, MaintenanceJobFacade) else job)


def claim_running(db: Session, job_id: int, kind: str, started_at: datetime) -> int:
    """Conditionally mark the job running, returning the number of rows
    claimed. The v2 services use this shape so two dispatches of the same id
    cannot both start work. A manual-start route (or a test simulating one,
    for either an Operation or a legacy row) pre-sets the row to "running"
    with no `started_at` before this ever runs, so "running" alone isn't
    "already claimed" - only a "running" row that already has a `started_at`
    is, and matching it here would let two concurrent claims both report
    success."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == kind)
        .first()
    )
    if operation is not None:
        return (
            db.query(Operation)
            .filter(
                Operation.id == job_id,
                or_(
                    Operation.status == "queued",
                    and_(
                        Operation.status == "running",
                        Operation.started_at.is_(None),
                    ),
                ),
            )
            .update(
                {"status": "running", "started_at": started_at},
                synchronize_session=False,
            )
        )
    model = LEGACY_MODELS[kind]
    return (
        db.query(model)
        .filter(
            model.id == job_id,
            or_(
                model.status == "pending",
                and_(model.status == "running", model.started_at.is_(None)),
            ),
        )
        .update(
            {"status": "running", "started_at": started_at},
            synchronize_session=False,
        )
    )


def maintenance_jobs_started_since(db: Session, kind: str, since: datetime) -> list:
    """Every `kind` job started at or after `since`, from both tables, newest
    first. A reader of recent history (the dashboard timeline) sees the
    operations rows this phase writes and the legacy rows written before it,
    until phase 9 drops the legacy table (spec section 14)."""
    model = _legacy_model(kind)
    operations = (
        db.query(Operation)
        .filter(Operation.kind == kind, Operation.started_at >= since)
        .all()
    )
    jobs = [MaintenanceJobFacade(db, operation) for operation in operations]
    jobs.extend(db.query(model).filter(model.started_at >= since).all())
    jobs.sort(key=lambda job: (job.started_at, job.id), reverse=True)
    return jobs


# A row still waiting for its verdict. `pending` is the legacy word for
# `queued` (spec 6.3); every other status is an outcome, `skipped` included,
# since its reason says what kept the run from happening.
UNSETTLED_STATUSES: frozenset[str] = frozenset({"pending", "queued", "running"})


def _legacy_model(kind: str):
    model = LEGACY_MODELS.get(kind)
    if model is None:
        raise ValueError(f"Not a maintenance kind: {kind!r}")
    return model


def latest_maintenance_jobs_by_repository(
    db: Session, kind: str, repository_ids: list[int], *, settled: bool = False
) -> dict[int, Any]:
    """The newest `kind` row of each repository, from both tables. Newest by
    creation, as the legacy max-id lookup was; an operation wins a tie, since
    it is the row still being written.

    With `settled`, only rows that reached a verdict count: a queued run can
    wait hours for a runner slot and must not hide the failure before it, so
    a health reading asks for the verdict separately from the live row."""
    if not repository_ids:
        return {}
    model = _legacy_model(kind)
    legacy_filters = [model.repository_id.in_(repository_ids)]
    op_filters = [Operation.kind == kind, Operation.repository_id.in_(repository_ids)]
    if settled:
        # a legacy status column is nullable; NULL is not "still waiting"
        legacy_filters.append(
            or_(model.status.is_(None), model.status.notin_(UNSETTLED_STATUSES))
        )
        op_filters.append(Operation.status.notin_(UNSETTLED_STATUSES))
    result: dict[int, Any] = {}
    for job in newest_per_group(
        db,
        model,
        model.repository_id,
        func.coalesce(model.created_at, datetime.min),
        legacy_filters,
    ):
        result[job.repository_id] = job
    for operation in newest_per_group(
        db, Operation, Operation.repository_id, Operation.created_at, op_filters
    ):
        current = result.get(operation.repository_id)
        if current is None or operation.created_at >= (
            current.created_at or datetime.min
        ):
            result[operation.repository_id] = MaintenanceJobFacade(db, operation)
    return result
