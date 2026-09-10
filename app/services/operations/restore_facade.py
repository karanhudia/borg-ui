"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
restore-job attribute surface.

`restore_service` and the restore routes drive a job through a fixed set of
attributes. Phase 7 moves the row to `operations` without rewriting them:
`resolve_restore_job()` hands them this facade.

Three legacy columns have no column of their own here. `progress` (an int) is
`operations.progress_percent`; `estimated_time_remaining` is arithmetic over
the sizes and the speed, exactly the arithmetic the service performs before
assigning it; `logs`, which the service builds once at the end, goes to the
operation's log file (spec 6.1), which the Activity log routes and log
retention already read and expire.
"""

import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, Repository
from app.services.operations.details import restore_details

CANCELLED_BY_USER = json.dumps({"key": "backend.errors.restore.cancelledByUser"})
CANCELLED_PROCESS_NOT_FOUND = json.dumps(
    {"key": "backend.errors.restore.cancelledByUserProcessNotFound"}
)
CANCEL_MESSAGES = (CANCELLED_BY_USER, CANCELLED_PROCESS_NOT_FOUND)

_BYTES_PER_MB = 1024 * 1024

# Spec 6.2 columns that live on the details row and need no translation.
# `current_file` is not here: it has a property below so the Background work
# board's progress message follows it.
_DETAIL_FIELDS = (
    "archive",
    "destination",
    "destination_type",
    "destination_connection_id",
    "temp_extraction_path",
    "destination_hostname",
    "repository_type",
    "original_size",
    "restored_size",
    "restore_speed",
    "nfiles",
)


class RestoreJobFacade:
    """One `Operation` presented as a legacy restore job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "_details", restore_details(db, operation))

    def __setattr__(self, name: str, value) -> None:
        # A restore-specific column lives on the details row, not on this
        # object, so a plain `object.__setattr__` would silently drop it.
        # Everything else (status, progress, ...) is a real property below
        # and goes through the normal descriptor path.
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "_details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        # Only reached when normal lookup fails, so every property below wins.
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "_details"), name)
        raise AttributeError(f"restore operations carry no {name!r}")

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
        """The repository path, which is what the legacy row stored and what
        the routes still answer under this name."""
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
        return self._details.current_file

    @current_file.setter
    def current_file(self, value) -> None:
        self._details.current_file = value
        self.operation.progress_message = value or None

    @property
    def estimated_time_remaining(self) -> int:
        speed = self._details.restore_speed or 0.0
        remaining = (self._details.original_size or 0) - (
            self._details.restored_size or 0
        )
        if remaining <= 0 or speed <= 0:
            return 0
        return int((remaining / _BYTES_PER_MB) / speed)

    @estimated_time_remaining.setter
    def estimated_time_remaining(self, value) -> None:
        """Derived from the sizes and the speed the service also writes; the
        legacy column stored the result of the same arithmetic. Accepted and
        dropped."""
        return None

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
        """The service captures the process output and assigns it once, at the
        end. The operation keeps it in its log file rather than on the row."""
        from app.services.operations.runner import operation_log_path

        if value is None:
            return
        path = (
            Path(self.operation.log_file_path)
            if self.operation.log_file_path
            else operation_log_path(self.operation.id)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        self.operation.log_file_path = str(path)


def resolve_restore_job(db: Session, job_id: int) -> Optional["RestoreJobFacade"]:
    """The job a restore caller should drive for `job_id`, or None when no
    restore operation has the id."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "restore")
        .first()
    )
    if operation is None:
        return None
    return RestoreJobFacade(db, operation)


def list_restore_jobs(db: Session, limit: int) -> list:
    """The newest `limit` restore jobs, newest first, for the list route.
    The id is the tie-break, so rows sharing a timestamp still come back in a
    stable order."""
    operations = (
        db.query(Operation)
        .filter(Operation.kind == "restore")
        .order_by(Operation.created_at.desc(), Operation.id.desc())
        .limit(limit)
        .all()
    )
    return [RestoreJobFacade(db, op) for op in operations]
