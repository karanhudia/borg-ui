"""What a failed Borg run reports besides its exit code.

The failure report reaches the server on its own, before (or without) the
log lines the run produced: the lines travel over the session and can land
after the report, so a server that read Borg's reason from them recorded the
failure with the exit code alone. The report therefore carries a bounded
tail of what Borg wrote and says whether the failure was a lock another
process holds - the one failure the server treats as transient.
"""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Iterable
from typing import Any, Optional

# The logger Borg's progress indicators print through when another one
# runs (the cache transaction during a prune): a step, not a reason.
PROGRESS_LOGGER = "borg.output.progress"

FAILURE_KIND_LOCK_CONTENTION = "lock_contention"
FAILURE_KIND_OTHER = "other"

# The tail keeps the last lines of the run, bounded twice: Borg's usage
# block runs to dozens of lines before the one that says what was wrong,
# and a single line can be a whole traceback.
FAILURE_TAIL_LINES = 40
FAILURE_TAIL_CHARS = 4096

# Borg's modern exit codes for a lock another process holds: LockTimeout
# (73), and LockError / LockErrorT (70, 71) for a lock that could not be
# taken. Not LockFailed (72): the lock file could not be created (a
# read-only or foreign-owned repository), which waiting does not change;
# nor NotLocked / NotMyLock (74, 75), about a lock that is not there.
LOCK_CONTENTION_EXIT_CODES = (70, 71, 73)
# A Borg 1 run without modern exit codes says the same in words, under the
# legacy exit code 2 every error gets. LockFailed says
# "(Permission denied)" where LockTimeout says "(timeout)". Anchored at the
# line's end: a repository path may contain "(timeout)" itself.
_LOCK_CONTENTION_LINE = re.compile(
    r"Failed to create/acquire the lock .*\(timeout\)\.?\s*$", re.MULTILINE
)


def plain_line(line: str) -> Optional[str]:
    """The line as the operator would read it: a `--log-json` message is
    its text, a progress event is nothing (it is not part of the reason),
    everything else is itself."""
    stripped = line.rstrip("\n")
    if not stripped.lstrip().startswith("{"):
        return stripped
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if not isinstance(payload, dict):
        return stripped
    if payload.get("type") == "log_message":
        if payload.get("name") == PROGRESS_LOGGER:
            # a progress step printed through the logger (agent 0.1.9)
            return None
        message = payload.get("message")
        return message if isinstance(message, str) else None
    if payload.get("type") in {
        "archive_progress",
        "progress_message",
        "progress_percent",
        "file_status",
    }:
        return None
    return stripped


class FailureTail:
    """The last plain lines of a run, kept as it goes. A line is filtered
    before it takes a slot: progress events (dozens between two messages)
    must not push the reason out of the bounded buffer."""

    def __init__(self) -> None:
        self._lines: deque[str] = deque(maxlen=FAILURE_TAIL_LINES)

    def append(self, line: str) -> None:
        plain = plain_line(line)
        if plain is not None and plain.strip():
            self._lines.append(plain.rstrip())

    def lines(self) -> list[str]:
        return list(self._lines)


def bounded_text(lines: list[str]) -> str:
    """The newest of `lines` that fit the character bound as whole lines.
    A line is never cut: the server redacts a repository location with
    credentials from the text, and a cut anywhere through the location can
    leave the credential unrecognisable. A line beyond the bound on its own
    is not sent; its length stands in for it, and the lines before it (a
    reason ahead of an oversized traceback line) are still kept."""
    kept: list[str] = []
    size = 0
    for line in reversed(lines):
        if len(line) > FAILURE_TAIL_CHARS:
            line = f"[a line of {len(line)} characters was left out]"
        extra = len(line) + (1 if kept else 0)
        if size + extra > FAILURE_TAIL_CHARS:
            break
        kept.append(line)
        size += extra
    return "\n".join(reversed(kept))


def failure_tail(lines: Iterable[str]) -> str:
    """The last non-empty plain lines of the run, within both bounds."""
    kept = FailureTail()
    for line in lines:
        kept.append(line)
    return bounded_text(kept.lines())


# The exit codes that do not say what went wrong: a Borg 1 on legacy exit
# codes ends every error with 2, and a run that ended without one.
_INCONCLUSIVE_EXIT_CODES = (None, 2)
# Borg 2 raises LockTimeout (73, the timeout line) for a lock of its own
# that another borg killed meanwhile, too - a run that must not go on,
# and nothing a wait changes.
_LOCK_LOST_LINE = re.compile(r"Our lock was killed by another borg")


def failure_kind(return_code: Optional[int], tail: str) -> str:
    """Lock contention by the exit code, or by Borg's own words only when
    the exit code does not tell (a Borg 1 on legacy exit codes): a modern
    code names the first error, and a later timeout line does not turn a
    lock file Borg could not create (72) into contention. A lock of the
    run's own that was killed is not contention either."""
    if _LOCK_LOST_LINE.search(tail):
        return FAILURE_KIND_OTHER
    if isinstance(return_code, int) and return_code in LOCK_CONTENTION_EXIT_CODES:
        return FAILURE_KIND_LOCK_CONTENTION
    if return_code in _INCONCLUSIVE_EXIT_CODES and _LOCK_CONTENTION_LINE.search(tail):
        return FAILURE_KIND_LOCK_CONTENTION
    return FAILURE_KIND_OTHER


def failure_report(
    return_code: Optional[int], output: str | Iterable[str]
) -> dict[str, Any]:
    """The report's `stderr_tail` and `failure_kind` for a Borg run that
    ended with `return_code`, from what it wrote (a text, or its lines).
    The kind is read from the last lines before the character bound cuts
    them: a long lock line loses its head, not its meaning."""
    lines = output.splitlines() if isinstance(output, str) else output
    kept = FailureTail()
    for line in lines:
        kept.append(line)
    plain_lines = kept.lines()
    return {
        "stderr_tail": bounded_text(plain_lines),
        "failure_kind": failure_kind(return_code, "\n".join(plain_lines)),
    }
