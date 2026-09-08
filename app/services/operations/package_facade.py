"""An `operations` row wearing the legacy package-install-job surface.

Spec 6.2 gives `package_install` no extension table, so the input
(`package_id`) lives in `operations.params`, the exit code in
`operations.result`, and the captured output in the operation's log file. The
two streams are separated by sentinel lines this module writes and parses, so
`GET /api/packages/jobs/{id}` keeps returning `stdout` and `stderr` apart.

The kind is category `system` with a null `repository_id` (spec 6.3).

Deleted in phase 9 with the legacy table.
"""

from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, PackageInstallJob

# Deliberately unlikely to appear in apt output, and written by this module
# alone, so the split below is deterministic.
STDOUT_SENTINEL = "===== BORG-UI PACKAGE STDOUT ====="
STDERR_SENTINEL = "===== BORG-UI PACKAGE STDERR ====="

ACTIVE_STATUSES = ("queued", "running")
# Pre-phase-6 rows only; goes away with the table in phase 9.
_LEGACY_ACTIVE_STATUSES = ("pending", "installing")

_TO_OPERATION = {"pending": "queued", "installing": "running"}
_TO_LEGACY = {"queued": "pending", "running": "installing"}


class PackageInstallFacade:
    """One `Operation` presented as a legacy package install job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)

    # -- identity ----------------------------------------------------------

    @property
    def id(self) -> int:
        return self.operation.id

    @property
    def package_id(self) -> Optional[int]:
        return (self.operation.params or {}).get("package_id")

    @property
    def created_at(self):
        return self.operation.created_at

    # -- lifecycle ---------------------------------------------------------

    @property
    def status(self) -> str:
        return _TO_LEGACY.get(self.operation.status, self.operation.status)

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = _TO_OPERATION.get(value, value)

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

    # -- process ownership -------------------------------------------------

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
        self.operation.process_start_time = None if value is None else float(value)

    # -- result ------------------------------------------------------------

    @property
    def exit_code(self):
        return (self.operation.result or {}).get("exit_code")

    @exit_code.setter
    def exit_code(self, value) -> None:
        result = dict(self.operation.result or {})
        result["exit_code"] = value
        self.operation.result = result

    # -- captured output ---------------------------------------------------

    @property
    def log_file_path(self):
        return self.operation.log_file_path

    def write_output(self, stdout: str, stderr: str) -> None:
        from app.services.operations.runner import operation_log_path

        path = Path(
            self.operation.log_file_path or operation_log_path(self.operation.id)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{STDOUT_SENTINEL}\n{stdout or ''}\n{STDERR_SENTINEL}\n{stderr or ''}",
            encoding="utf-8",
        )
        self.operation.log_file_path = str(path)

    def _streams(self) -> tuple[str, str]:
        path = self.operation.log_file_path
        if not path:
            return "", ""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            return "", ""
        if not text.startswith(f"{STDOUT_SENTINEL}\n"):
            # A log written by something other than write_output (the runner's
            # ctx.log, say). Treat the whole file as stdout.
            return text, ""
        rest = text[len(STDOUT_SENTINEL) + 1 :]
        stdout, separator, stderr = rest.partition(f"\n{STDERR_SENTINEL}\n")
        if not separator:
            return rest, ""
        return stdout, stderr

    @property
    def stdout(self) -> str:
        return self._streams()[0]

    @property
    def stderr(self) -> str:
        return self._streams()[1]

    @property
    def logs(self) -> str:
        """The combined text, for a reader that wants one stream."""
        stdout, stderr = self._streams()
        return "\n".join(part for part in (stdout, stderr) if part)


def resolve_package_job(db: Session, job_id: int) -> Any:
    """The job a package caller should drive for `job_id`. Operations win; an
    id written before this phase falls back to the legacy table."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "package_install")
        .first()
    )
    if operation is not None:
        return PackageInstallFacade(db, operation)
    return db.query(PackageInstallJob).filter(PackageInstallJob.id == job_id).first()


def active_package_install(db: Session, package_id: int) -> Any:
    """The queued or running install for this package, if any.

    Params are scanned in Python because a JSON column is not portably
    queryable across SQLite and PostgreSQL, the same shape phase 5 used for
    `active_delete_for_archive`.
    """
    for operation in (
        db.query(Operation)
        .filter(
            Operation.kind == "package_install",
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Operation.id.desc())
        .all()
    ):
        if (operation.params or {}).get("package_id") == package_id:
            return PackageInstallFacade(db, operation)
    return (
        db.query(PackageInstallJob)
        .filter(
            PackageInstallJob.package_id == package_id,
            PackageInstallJob.status.in_(_LEGACY_ACTIVE_STATUSES),
        )
        .first()
    )
