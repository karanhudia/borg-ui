"""The SIGTERM/wait/SIGKILL routine the tracking services share."""

import asyncio
import os
import signal
import sys
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.process_cancel import (
    communicate_or_kill,
    terminate_process,
    terminate_tracked_process,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_nothing_tracked_is_false_not_an_error():
    """`cancel_watcher` reads a `False` as "not started yet, poll again", so
    an untracked job must come back rather than raise."""
    assert await terminate_tracked_process({}, 7, "prune") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_process_that_exits_on_sigterm_is_not_killed():
    process = MagicMock()
    process.pid = 111
    process.wait = AsyncMock(return_value=None)

    assert await terminate_tracked_process({7: process}, 7, "prune") is True
    process.terminate.assert_called_once()
    process.kill.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_process_that_ignores_sigterm_is_killed(monkeypatch):
    """The grace period is the only thing standing between a wedged Borg and
    a repository lane held forever, so the SIGKILL escalation has to fire."""
    monkeypatch.setattr("app.services.process_cancel._GRACE_SECONDS", 0.01)
    process = MagicMock()
    process.pid = 222
    waits = [asyncio.Event().wait(), None]

    async def wait():
        result = waits.pop(0)
        if result is None:
            return None
        await result

    process.wait = wait

    assert await terminate_tracked_process({7: process}, 7, "prune") is True
    process.terminate.assert_called_once()
    process.kill.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_process_that_raises_on_terminate_is_false():
    """An already-reaped process raises; the caller keeps polling."""
    process = MagicMock()
    process.pid = 333
    process.terminate.side_effect = ProcessLookupError("no such process")

    assert await terminate_tracked_process({7: process}, 7, "prune") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_terminate_process_takes_a_process_the_caller_already_holds():
    """The services call this from inside their own run, where the process is
    a local rather than a `running_processes` entry."""
    process = MagicMock()
    process.pid = 444
    process.wait = AsyncMock(return_value=None)

    assert await terminate_process(process, 7, "borg2 check") is True
    process.terminate.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_task_does_not_wait_forever_on_a_wedged_process(monkeypatch):
    """The `except asyncio.CancelledError` handlers used to be `terminate()`
    followed by a bare `await process.wait()`: no timeout and no SIGKILL, so a
    Borg that ignores SIGTERM (it installs a handler to unlock the repository
    cleanly) hung the task and held the lane forever. Going through the shared
    routine gives those paths the escalation."""
    monkeypatch.setattr("app.services.process_cancel._GRACE_SECONDS", 0.01)
    process = MagicMock()
    process.pid = 555
    ignored_sigterm = asyncio.Event()

    async def wait():
        if not process.kill.called:
            await ignored_sigterm.wait()
        return None

    process.wait = wait

    result = await asyncio.wait_for(terminate_process(process, 7, "prune"), timeout=2.0)

    assert result is True
    process.kill.assert_called_once()


@pytest.fixture
def slow_children(monkeypatch):
    """Every subprocess becomes a `sleep 30` that outlasts the runner's
    timeout; the started processes are collected for the assertions."""
    started = []
    real_exec = asyncio.create_subprocess_exec

    async def fake_exec(*_args, **kwargs):
        process = await real_exec(
            "sleep",
            "30",
            stdin=kwargs.get("stdin"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        started.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    yield started
    for process in started:
        if process.returncode is None:
            process.kill()


@pytest.mark.unit
async def test_communicate_or_kill_ends_its_child_on_timeout():
    process = await asyncio.create_subprocess_exec(
        "sleep", "30", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
    )
    with pytest.raises(asyncio.TimeoutError):
        await communicate_or_kill(process, timeout=0.2, input=b"")
    # SIGTERM, not SIGKILL: Borg releases its lock on SIGTERM.
    assert process.returncode == -signal.SIGTERM


@pytest.mark.unit
async def test_communicate_or_kill_kills_a_child_that_ignores_sigterm(monkeypatch):
    monkeypatch.setattr("app.services.process_cancel._GRACE_SECONDS", 0.2)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(30)",
        stdout=asyncio.subprocess.PIPE,
    )
    await process.stdout.readline()
    with pytest.raises(asyncio.TimeoutError):
        await communicate_or_kill(process, timeout=0.2)
    assert process.returncode == -signal.SIGKILL


@pytest.mark.unit
async def test_communicate_or_kill_reaps_a_child_whose_output_filled_the_pipe(
    monkeypatch,
):
    """asyncio reports the exit only once both pipes are closed. A child that
    keeps writing through the SIGTERM grace period fills the reader's buffer,
    the reader pauses, and nothing reads the EOF once `communicate` is
    cancelled; without draining, the reap never returns."""
    monkeypatch.setattr("app.services.process_cancel._GRACE_SECONDS", 0.5)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import signal, sys; signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True: sys.stdout.write('x' * 65536)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    started = time.monotonic()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(communicate_or_kill(process, timeout=0.5), 10)
        # The 0.5 s deadline plus the grace period, not the 10 s guard.
        assert time.monotonic() - started < 5
        assert process.returncode is not None
    finally:
        if process.returncode is None:
            process.kill()


@pytest.mark.unit
async def test_communicate_or_kill_ends_its_child_on_cancellation():
    process = await asyncio.create_subprocess_exec(
        "sleep", "30", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
    )
    task = asyncio.create_task(communicate_or_kill(process, timeout=30, input=b""))
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.returncode is not None
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.unit
async def test_a_timed_out_repository_command_ends_its_borg(slow_children, monkeypatch):
    """#1259: the info and archive list routes answered while Borg kept
    running and kept its lock."""
    from app.api import repositories

    monkeypatch.setattr(
        repositories, "_prepare_repository_borg_env", lambda *a, **k: ({}, None)
    )
    with pytest.raises(asyncio.TimeoutError):
        await repositories._run_repository_command(
            MagicMock(), MagicMock(), ["borg", "info"], 0.2
        )
    assert [p.returncode is not None for p in slow_children] == [True]


@pytest.mark.unit
async def test_a_timed_out_borg1_command_ends_its_borg(slow_children):
    from app.core.borg import BorgInterface

    result = await BorgInterface()._execute_command(["borg", "info"], timeout=0.2)
    assert result["success"] is False
    assert [p.returncode is not None for p in slow_children] == [True]


@pytest.mark.unit
async def test_a_timed_out_borg2_command_ends_its_borg(slow_children):
    from app.core.borg2 import Borg2Interface

    result = await Borg2Interface()._run(["borg2", "info"], timeout=0.2)
    assert result["success"] is False
    assert [p.returncode is not None for p in slow_children] == [True]


@pytest.mark.unit
async def test_communicate_or_kill_gives_up_on_a_pipe_a_grandchild_holds(
    monkeypatch,
):
    """Borg's ssh inherits its stderr; a pipe held past SIGKILL must not keep
    the caller waiting for as long as the grandchild lives."""
    monkeypatch.setattr("app.services.process_cancel._GRACE_SECONDS", 0.2)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import signal, subprocess, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "child = subprocess.Popen(['sleep', '30'])\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(30)",
        stdout=asyncio.subprocess.PIPE,
    )
    grandchild = int(await process.stdout.readline())
    started = time.monotonic()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(communicate_or_kill(process, timeout=0.2), 10)
        assert time.monotonic() - started < 5
        assert process.returncode == -signal.SIGKILL
    finally:
        os.kill(grandchild, signal.SIGKILL)
