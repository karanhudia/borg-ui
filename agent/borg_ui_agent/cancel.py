"""Cancelling a running job's process, whatever it prints (0.1.7)."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Callable
from typing import Any, Optional

# Advertised by an agent whose jobs of the kinds below stop when they are
# cancelled while their process prints nothing.
CANCEL_CAPABILITY = "jobs.cancel"

# The kinds that end their process on cancel and report `canceled`
# themselves; the session leaves their cancel report to them. The streamed
# artifact kinds (extract, tar export, diff) have polled their cancel since
# they exist.
SELF_CANCELLING_JOB_KINDS = frozenset(
    {
        "backup.create",
        "repository.check",
        "repository.prune",
        "repository.compact",
        "repository.restore",
        "repository.delete_archive",
        # also run by the streaming path, which reports its own cancel
        "repository.init",
        "repository.rclone_sync",
    }
)

# The server reaps an in-flight job after fifteen minutes without activity
# (app/services/agent_job_reaper.py), and a silent Borg reports nothing: a
# reaped job can no longer be cancelled while Borg runs on. The job reports
# an empty progress this often instead.
KEEPALIVE_SECONDS = 60

# After `terminate` returned (it waits up to ten seconds for the leader
# itself), how much longer the worker may still be reading output before
# the whole process group is killed: a wrapper's child that ignores
# SIGTERM would keep the pipes, and the worker, open forever.
KILL_GROUP_AFTER_SECONDS = 10

# How often a running command's cancel poller asks `should_cancel`. The
# check may be a heartbeat request (the polling runtime throttles it to one
# every few seconds itself); on the session transport it reads an event.
CANCEL_POLL_SECONDS = 0.5


def cancel_requested(should_cancel: Optional[Callable[[], bool]]) -> bool:
    """Ask `should_cancel`; a check that fails (the polling runtime's
    heartbeat while the server is unreachable) is unknown, not cancelled."""
    if should_cancel is None:
        return False
    try:
        return bool(should_cancel())
    except Exception:  # noqa: BLE001 - unknown is not cancelled
        return False


def start_cancel_poller(
    process: subprocess.Popen,
    should_cancel: Optional[Callable[[], bool]],
    done: threading.Event,
    terminate: Callable[[subprocess.Popen], Any],
) -> threading.Event:
    """Poll `should_cancel` on its own thread until `done` is set or the
    process exits, and `terminate` the process once a cancel is requested.
    Returns the event the poller sets when it did.

    A thread rather than a check per output line: Borg can be silent for a
    long time (a lock wait, a stalled store, a compact), and a cancel must
    still reach it."""
    cancelled = threading.Event()
    if should_cancel is None:
        return cancelled

    def _poll() -> None:
        while not done.wait(CANCEL_POLL_SECONDS):
            if process.poll() is not None:
                return
            if cancel_requested(should_cancel):
                # The check may have waited on the server while the process
                # ended and was reaped; its pid may belong to another process
                # by now, so only a live one is ended.
                if done.is_set() or process.poll() is not None:
                    return
                cancelled.set()
                terminate(process)
                if not done.wait(KILL_GROUP_AFTER_SECONDS):
                    kill_process_group(process)
                return

    threading.Thread(target=_poll, daemon=True).start()
    return cancelled


def start_keepalive(
    process: subprocess.Popen,
    client: Any,
    job_id: int,
    done: threading.Event,
    *,
    seconds: Optional[float] = None,
) -> None:
    """Report an empty progress for `job_id` every `seconds` (default
    `KEEPALIVE_SECONDS`) until `done` is set or the process exits. A thread
    of its own: on the polling transport a send is an HTTP request with
    retries, which must not hold the cancel poller. A send that fails is
    dropped; the next one is due a period later. No fields: every field the
    progress schema offers is a statistic that would be read as one."""
    interval = seconds if seconds is not None else KEEPALIVE_SECONDS

    def _loop() -> None:
        while not done.wait(interval):
            if process.poll() is not None:
                return
            try:
                client.send_progress(job_id, {})
            except Exception:  # noqa: BLE001 - a keepalive is best effort
                pass

    threading.Thread(target=_loop, daemon=True).start()


def kill_process_group(process: subprocess.Popen) -> None:
    """SIGKILL what is left of the process's group. The callers start their
    command in a session of its own, so the group id is the leader's pid.
    While a member lives the kernel does not hand that pid out again, so the
    group is signalled only if it still exists; an empty group has nothing
    left to kill, and its pid may already belong to a new process. (The two
    calls leave a window of one system call.)"""
    if os.name != "posix":
        try:
            process.kill()
        except OSError:
            pass
        return
    try:
        os.killpg(process.pid, 0)
    except OSError:
        return  # no member left
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass
