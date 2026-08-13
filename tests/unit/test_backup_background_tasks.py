"""A fire-and-forget backup task must not vanish mid-execution.

asyncio keeps only a weak reference to a bare ``create_task()`` result, so an
unreferenced backup task can be garbage-collected before it runs — leaving the
job stuck in ``pending`` (the root cause of a flaky backup integration test).
``app.api.backup._run_in_background`` holds a strong reference until the task
finishes; these tests pin that contract.
"""

import asyncio

import pytest

from app.api.backup import _background_tasks, _run_in_background


async def test_reference_held_during_execution_and_released_after():
    release = asyncio.Event()
    running = asyncio.Event()

    async def work():
        running.set()
        await release.wait()

    task = _run_in_background(work())
    await running.wait()
    assert task in _background_tasks  # strong reference retained while running

    release.set()
    await task
    assert task not in _background_tasks  # discarded once done


async def test_reference_released_even_when_task_raises():
    async def boom():
        raise RuntimeError("backup blew up")

    task = _run_in_background(boom())
    with pytest.raises(RuntimeError):
        await task
    assert task not in _background_tasks  # no leak on failure
