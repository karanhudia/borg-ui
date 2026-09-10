"""An `operations` row wearing the legacy package-install-job surface.

Spec 6.2 gives `package_install` no extension table, so the input
(`package_id`) lives in `operations.params`, the exit code in
`operations.result`, and the captured output in the operation's log file. The
file opens with one header line carrying the length of each stream, so the
split never depends on what apt printed, and `GET /api/packages/jobs/{id}`
keeps returning `stdout` and `stderr` apart.

The kind is category `system` with a null `repository_id` (spec 6.3).
"""

import re
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation

# First line of a log file this module wrote. The lengths are in characters
# of the decoded text, which is what the file holds after the newline.
_HEADER_PREFIX = "BORG-UI PACKAGE OUTPUT v1"
_HEADER = re.compile(rf"^{re.escape(_HEADER_PREFIX)} stdout=(\d+) stderr=(\d+)\n")

ACTIVE_STATUSES = ("queued", "running")

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
        stdout = stdout or ""
        stderr = stderr or ""
        path.write_text(
            f"{_HEADER_PREFIX} stdout={len(stdout)} stderr={len(stderr)}\n"
            f"{stdout}{stderr}",
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
        header = _HEADER.match(text)
        if header is None:
            # A log written by something other than write_output (the runner's
            # ctx.log, say). Treat the whole file as stdout.
            return text, ""
        body = text[header.end() :]
        stdout_len, stderr_len = int(header.group(1)), int(header.group(2))
        return body[:stdout_len], body[stdout_len : stdout_len + stderr_len]

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


def resolve_package_job(db: Session, job_id: int) -> Optional["PackageInstallFacade"]:
    """The job a package caller should drive for `job_id`, or None when no
    package install operation has the id."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "package_install")
        .first()
    )
    if operation is None:
        return None
    return PackageInstallFacade(db, operation)


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
    return None
