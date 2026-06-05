import asyncio
import threading
import weakref
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

_locks: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[tuple[int, str], asyncio.Lock]
] = weakref.WeakKeyDictionary()
_locks_guard = threading.Lock()


async def _get_lock(repo_id: int, scope: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    key = (repo_id, scope)
    with _locks_guard:
        loop_locks = _locks.setdefault(loop, {})
        lock = loop_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            loop_locks[key] = lock
        return lock


async def acquire_repository_command_lock(
    repo_id: int,
    *,
    scope: str = "metadata",
) -> asyncio.Lock:
    lock = await _get_lock(repo_id, scope)
    await lock.acquire()
    return lock


async def run_serialized_repository_command(
    repo_id: int,
    operation: Callable[[], Awaitable[T]],
    *,
    scope: str = "metadata",
) -> T:
    """
    Serialize repository-scoped Borg commands that can contend on Borg locks.

    Borg can require exclusive repository or local cache locks even for
    read-only commands like `info` and `list`, especially on SSH/remote
    repositories. Queueing commands per repository avoids those races without
    blocking unrelated repositories.
    """
    lock = await _get_lock(repo_id, scope)
    async with lock:
        return await operation()
