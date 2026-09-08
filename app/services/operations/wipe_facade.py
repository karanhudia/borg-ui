"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
repository-wipe attribute surface.

`repository_wipe_service` and the wipe routes drive a job through a fixed set
of attributes. Phase 6 moves the row to `operations` without rewriting them:
`resolve_wipe_job()` hands them this facade for new work and the real
`RepositoryWipeJob` for an id written before this phase.

Two wipe statuses do not exist in spec 6.3 and the frontend switches on both,
so they are stored as their nearest spec status and reconstructed from
`details.phase`:

| legacy status | operation status | phase |
| --- | --- | --- |
| `completed_compaction_failed` | `completed_with_warnings` | `compact_failed` |
| `failed_partial` | `failed` | `delete_failed_partial` |

Deleted in phase 9 with the legacy table.
"""

from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, Repository, RepositoryWipeJob
from app.services.operations.details import wipe_details

ACTIVE_STATUSES = ("queued", "running")
# A pre-phase-6 install can restart mid-run and leave one of these behind.
# Nothing writes them any more; the tuple goes away in phase 9.
_LEGACY_ACTIVE_STATUSES = ("pending", "running")

PHASE_COMPACT_FAILED = "compact_failed"
PHASE_DELETE_FAILED_PARTIAL = "delete_failed_partial"

_TO_OPERATION = {
    "pending": "queued",
    "completed_compaction_failed": "completed_with_warnings",
    "failed_partial": "failed",
}
_PHASE_FOR_STATUS = {
    "completed_compaction_failed": PHASE_COMPACT_FAILED,
    "failed_partial": PHASE_DELETE_FAILED_PARTIAL,
}
_DETAIL_FIELDS = (
    "phase",
    "archive_count",
    "archive_fingerprint",
    "archive_manifest_json",
    "dry_run_output",
    "blocking_reason",
    "protected_archives_json",
    "run_compact",
    "requested_by_user_id",
    "confirmed_by_user_id",
    "confirmed_at",
)


class WipeJobFacade:
    """One `Operation` presented as a legacy repository wipe job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "_details", wipe_details(db, operation))

    def __setattr__(self, name: str, value) -> None:
        # A wipe-specific column lives on the details row, not on this object,
        # so a plain `object.__setattr__` would silently drop it. Everything
        # else (status, progress, ...) is a real property below and goes
        # through the normal descriptor path.
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "_details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        # Only reached when normal lookup fails, so every property below wins.
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "_details"), name)
        raise AttributeError(f"wipe operations carry no {name!r}")

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
        status = self.operation.status
        phase = self._details.phase
        if status == "queued":
            return "pending"
        if status == "completed_with_warnings" and phase == PHASE_COMPACT_FAILED:
            return "completed_compaction_failed"
        if status == "failed" and phase == PHASE_DELETE_FAILED_PARTIAL:
            return "failed_partial"
        return status

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = _TO_OPERATION.get(value, value)
        phase = _PHASE_FOR_STATUS.get(value)
        if phase is not None:
            self._details.phase = phase

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
        """The legacy table kept a truncated text mirror alongside the file.
        The operation keeps only the file, and the service writes that file
        itself, so this is accepted and dropped rather than clobbering it."""
        return None

    @property
    def has_logs(self) -> bool:
        return bool(self.operation.log_file_path)

    @has_logs.setter
    def has_logs(self, value) -> None:
        """Derived from the file. Accepted and dropped so a service that sets
        it alongside `logs` keeps working."""
        return None


def resolve_wipe_job(db: Session, job_id: int) -> Any:
    """The job a wipe caller should drive for `job_id`.

    Operations win, so new work runs on the new table. Ids that belong to a
    row written before this phase fall back to the legacy table, which keeps
    the wipe status route working for history and for previews.
    """
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "wipe")
        .first()
    )
    if operation is not None:
        return WipeJobFacade(db, operation)
    return db.query(RepositoryWipeJob).filter(RepositoryWipeJob.id == job_id).first()


def active_wipe_operation(db: Session, repository_id: int) -> Any:
    """Queued or running wipe work on this repository, operations first, then
    a legacy row a pre-phase-6 install left active. A `previewed` legacy row is
    deliberately not active: a preview holds no lock and blocks nothing."""
    operation = (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "wipe",
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Operation.id.desc())
        .first()
    )
    if operation is not None:
        return operation
    return (
        db.query(RepositoryWipeJob)
        .filter(
            RepositoryWipeJob.repository_id == repository_id,
            RepositoryWipeJob.status.in_(_LEGACY_ACTIVE_STATUSES),
        )
        .order_by(RepositoryWipeJob.id.desc())
        .first()
    )
