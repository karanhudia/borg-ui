"""Shared job polling helpers for integration and smoke tests."""

from __future__ import annotations

import time
from typing import Callable, Optional


def wait_for_payload_status(
    fetch_payload: Callable[[], dict],
    *,
    expected: set[str],
    timeout: float,
    poll_interval: float = 0.25,
    terminal: Optional[set[str]] = None,
    status_field: str = "status",
    description: str = "job",
) -> dict:
    """Poll a payload source until it reaches an expected status."""
    deadline = time.time() + timeout
    last_payload = None
    terminal_statuses = terminal or {"completed", "completed_with_warnings", "failed", "cancelled"}
    while time.time() < deadline:
        last_payload = fetch_payload()
        status = last_payload.get(status_field)
        if status in expected:
            return last_payload
        if status in terminal_statuses and status not in expected:
            raise TimeoutError(f"{description} reached unexpected status {status}: {last_payload}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Timed out waiting for {description}: {last_payload}")


def wait_for_running_payload(
    fetch_payload: Callable[[], dict],
    *,
    timeout: float,
    poll_interval: float = 0.25,
    status_field: str = "status",
    description: str = "job",
) -> dict:
    """Poll a payload source until it reports running."""
    return wait_for_payload_status(
        fetch_payload,
        expected={"running"},
        timeout=timeout,
        poll_interval=poll_interval,
        terminal=set(),
        status_field=status_field,
        description=description,
    )
