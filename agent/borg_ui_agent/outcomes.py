"""Job outcomes the server has not acknowledged yet (#1377).

A finished job's outcome stays here until the server has answered its
report. Until then the job is listed in ``running_job_ids`` (hello and
session heartbeat), so the server does not run it again while the report
is on its way. The outcomes live in this process: an agent that restarts
before the server is back loses them, and the server then decides by its
own rules whether the job runs again.
"""

from __future__ import annotations

import threading
from typing import Any


class KeptOutcomes:
    """Thread-safe: workers, the session thread and the delivery thread
    all use it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._outcomes: dict[int, dict[str, Any]] = {}

    def keep(self, job_id: int, kind: str, body: dict[str, Any]) -> None:
        """Keep `job_id`'s outcome until the server acknowledges it."""
        with self._lock:
            self._outcomes[job_id] = {"kind": kind, "body": body}

    def acknowledge(self, job_id: int) -> None:
        """The server has the outcome (or will never take it)."""
        with self._lock:
            self._outcomes.pop(job_id, None)

    def retrying_since(self, job_id: int, now: float) -> float:
        """When the server first answered `job_id`'s outcome with an error
        it might lift; `now` the first time."""
        with self._lock:
            outcome = self._outcomes.get(job_id)
            if outcome is None:
                return now
            return outcome.setdefault("retrying_since", now)

    def has(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._outcomes

    def pending(self) -> list[tuple[int, str, dict[str, Any]]]:
        with self._lock:
            return [
                (job_id, outcome["kind"], outcome["body"])
                for job_id, outcome in sorted(self._outcomes.items())
            ]

    def job_ids(self) -> set[int]:
        with self._lock:
            return set(self._outcomes)
