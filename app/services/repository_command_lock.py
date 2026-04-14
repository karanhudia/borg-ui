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


async def run_serialized_repository_command(
    repo_id: int,
    operation: Callable[[], Awaitable[T]],
    *,
    scope: str = "metadata",
) -> T:
    """
    Serialize repository-scoped Borg reads that can contend on the local cache.

    Borg can still require an exclusive local cache lock for read-only commands
    like `info` and `list`, especially on SSH/remote repositories. Queueing
    those commands per repository avoids the first-load race without blocking
    unrelated repositories.
    """
    lock = await _get_lock(repo_id, scope)
    async with lock:
        return await operation()
