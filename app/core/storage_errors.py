"""Recognize explicit storage failures without exposing private diagnostics."""

import errno
import re
import sqlite3
from typing import Literal

StorageFailure = Literal["full", "io", "corrupt", "unavailable"]

_FULL = re.compile(
    r"database or disk is full|\[Errno (?:28|122)\] (?:No space left on device|Disk quota exceeded)",
    re.IGNORECASE,
)
_IO = re.compile(r"\[Errno 5\] Input/output error", re.IGNORECASE)
# The database file is damaged, or the path holds something that is not one
# (dashboard c14412ebe3f63d01, 69fb9849b38044e3).
_CORRUPT = re.compile(
    r"database disk image is malformed|file is not a database", re.IGNORECASE
)
# SQLite cannot open or create the file: a missing or unwritable folder, a
# read-only mount (dashboard 9fc002dd6de5a4bb, 7eb1bfd0374046e6).
_UNAVAILABLE = re.compile(r"unable to open database file", re.IGNORECASE)
_SQLITE_CODES: dict[int, StorageFailure] = {
    sqlite3.SQLITE_FULL: "full",
    sqlite3.SQLITE_IOERR: "io",
    sqlite3.SQLITE_CORRUPT: "corrupt",
    sqlite3.SQLITE_NOTADB: "corrupt",
    sqlite3.SQLITE_CANTOPEN: "unavailable",
}


def storage_failure(error: BaseException | str) -> StorageFailure | None:
    """Inspect bounded exception chains, including SQLAlchemy's original error.

    Serialized Borg diagnostics have no exception object. Match their explicit
    OS error signatures only; an unrelated permission/lock error stays itself.
    """
    pending = [error]
    seen: set[int] = set()
    for _ in range(16):
        if not pending:
            break
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, OSError):
            if current.errno in (errno.ENOSPC, errno.EDQUOT):
                return "full"
            if current.errno == errno.EIO:
                return "io"
        if isinstance(current, sqlite3.Error):
            code = getattr(current, "sqlite_errorcode", 0) or 0
            if code & 0xFF in _SQLITE_CODES:
                return _SQLITE_CODES[code & 0xFF]
        original = getattr(current, "orig", None)
        cause = None
        if isinstance(current, BaseException):
            cause = current.__cause__
            if cause is None and not current.__suppress_context__:
                cause = current.__context__
        if not any(isinstance(e, BaseException) for e in (cause, original)):
            # SQLAlchemy wrapper text includes SQL and bound values, which
            # can be copied into outer exceptions too. Only inspect text
            # when no authoritative underlying exception is available.
            text = str(current)
            text = text[:8192] + text[-8192:]
            if _FULL.search(text):
                return "full"
            if _IO.search(text):
                return "io"
            if _CORRUPT.search(text):
                return "corrupt"
            if _UNAVAILABLE.search(text):
                return "unavailable"
        pending.extend(e for e in (cause, original) if isinstance(e, BaseException))
    return None


def storage_response(error: BaseException) -> tuple[int, dict] | None:
    failure = storage_failure(error)
    if failure is None:
        return None
    return (507 if failure == "full" else 503), {
        "key": f"backend.errors.storage.{failure}"
    }
