"""The SIGTERM/wait/SIGKILL routine the tracking services share."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.process_cancel import terminate_process, terminate_tracked_process


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
