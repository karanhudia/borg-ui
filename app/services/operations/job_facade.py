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
from typing import Any, Optional

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

# Only "pending" differs between the two vocabularies (spec 6.3); every other
# legacy word is already an operations word.
_LEGACY_TO_OPERATION = {"pending": "queued"}
_OPERATION_TO_LEGACY = {"queued": "pending"}


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
        return legacy_status(self.operation.status)

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = operation_status(value)

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


def refresh_job(db: Session, job: Any) -> None:
    """`db.refresh()` requires a mapped instance, which a facade is not: its
    mapped object is `.operation`. Callers hold either shape after
    `resolve_maintenance_job`, so route the refresh accordingly rather than
    let `Session.refresh` raise `UnmappedInstanceError` on a facade."""
    db.refresh(job.operation if isinstance(job, MaintenanceJobFacade) else job)


def claim_running(db: Session, job_id: int, kind: str, started_at: datetime) -> int:
    """Conditionally mark the job running, returning the number of rows
    claimed. The v2 services use this shape so two dispatches of the same id
    cannot both start work."""
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
                Operation.status.in_(("queued", "running")),
            )
            .update(
                {"status": "running", "started_at": started_at},
                synchronize_session=False,
            )
        )
    model = LEGACY_MODELS[kind]
    return (
        db.query(model)
        .filter(model.id == job_id, model.status.in_(("pending", "running")))
        .update(
            {"status": "running", "started_at": started_at},
            synchronize_session=False,
        )
    )
