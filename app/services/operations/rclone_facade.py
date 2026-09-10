"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
rclone-sync-job attribute surface.

One kind, `rclone_sync`, covers both the mirror sync and the cache hydrate;
which one it is lives in `details.operation`, per spec 6.2. The legacy
`triggered_by` word `initial` is not a spec 6.3 trigger, so it is stored as
`import` and mapped back here: the frontend switches on it
(`RunningCloudStorageJobsSection.tsx`). The initial sync is the only rclone
operation with that trigger, so the mapping round trips exactly.
"""

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation
from app.services.operations.details import rclone_details

LEGACY_TO_TRIGGER = {"initial": "import", "manual": "manual", "schedule": "schedule"}
TRIGGER_TO_LEGACY = {"import": "initial", "manual": "manual", "schedule": "schedule"}

_TO_OPERATION_STATUS = {"pending": "queued"}
_TO_LEGACY_STATUS = {"queued": "pending"}

_DETAIL_FIELDS = (
    "direction",
    "operation",
    "scheduled_for",
    "bytes_transferred",
    "files_transferred",
    "log_text",
    "error_text",
)


class RcloneSyncFacade:
    """One `Operation` presented as a legacy rclone sync job row."""

    def __init__(self, db: Session, operation: Operation):
        # The mapped row is `_row`, not `operation`: the legacy table has its
        # own `operation` column ("sync" or "hydrate"), and an attribute of
        # that name would shadow it on every read.
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "_row", operation)
        object.__setattr__(self, "_details", rclone_details(db, operation))

    @property
    def operation_row(self) -> Operation:
        """The mapped `Operation`, for a caller that needs the real row."""
        return self._row

    def __setattr__(self, name: str, value) -> None:
        # A rclone-specific column lives on the details row, not on this
        # object, so a plain `object.__setattr__` would silently drop it.
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "_details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        # Only reached when normal lookup fails, so every property below wins.
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "_details"), name)
        raise AttributeError(f"rclone_sync operations carry no {name!r}")

    # -- identity ----------------------------------------------------------

    @property
    def id(self) -> int:
        return self._row.id

    @property
    def kind(self) -> str:
        return self._row.kind

    @property
    def repository_id(self) -> Optional[int]:
        return self._row.repository_id

    @property
    def created_at(self):
        return self._row.created_at

    # -- lifecycle ---------------------------------------------------------

    @property
    def status(self) -> str:
        return _TO_LEGACY_STATUS.get(self._row.status, self._row.status)

    @status.setter
    def status(self, value: str) -> None:
        self._row.status = _TO_OPERATION_STATUS.get(value, value)

    @property
    def triggered_by(self) -> str:
        return TRIGGER_TO_LEGACY.get(self._row.trigger, self._row.trigger)

    @triggered_by.setter
    def triggered_by(self, value: str) -> None:
        self._row.trigger = LEGACY_TO_TRIGGER.get(value, value)

    @property
    def started_at(self):
        return self._row.started_at

    @started_at.setter
    def started_at(self, value) -> None:
        self._row.started_at = value

    @property
    def completed_at(self):
        return self._row.completed_at

    @completed_at.setter
    def completed_at(self, value) -> None:
        self._row.completed_at = value

    # -- logs --------------------------------------------------------------

    @property
    def log_path(self):
        """The legacy column name for what spec 6.1 calls log_file_path."""
        return self._row.log_file_path

    @log_path.setter
    def log_path(self, value) -> None:
        self._row.log_file_path = value


def rclone_activity_type(job: Any) -> str:
    """The Activity item type for a mirror job: one kind, two names."""
    return "rclone_hydrate" if job.operation == "hydrate" else "rclone_sync"


def resolve_rclone_job(
    db: Session, job_id: int, *, operation: Optional[str] = None
) -> Optional["RcloneSyncFacade"]:
    """The job a mirror caller should drive for `job_id`, or None when no
    rclone operation has the id or its sub-type is not the one asked for."""
    row = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "rclone_sync")
        .first()
    )
    if row is None:
        return None
    facade = RcloneSyncFacade(db, row)
    if operation is not None and facade.operation != operation:
        return None
    return facade
