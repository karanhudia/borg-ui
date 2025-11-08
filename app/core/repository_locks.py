"""
Repository lock manager for serializing Borg operations per repository.

This module provides a mechanism to prevent concurrent Borg operations on the same
repository, which can cause lock timeout errors when multiple requests try to access
a repository simultaneously (especially during cache building on cold starts).
"""

import asyncio
from typing import Dict, Callable, TypeVar, Union
import structlog
from functools import wraps

try:
    from typing import ParamSpec
except ImportError:
    from typing_extensions import ParamSpec

logger = structlog.get_logger()

# Global dictionary to store locks per repository
# Key: repository_id (int) or repository_path (str)
# Value: asyncio.Lock instance
_repository_locks: Dict[Union[int, str], asyncio.Lock] = {}

# Lock for managing the locks dictionary itself (lazily initialized)
_locks_dict_lock: Union[asyncio.Lock, None] = None


def _get_locks_dict_lock() -> asyncio.Lock:
    """Get or create the locks dictionary lock (lazy initialization)"""
    global _locks_dict_lock
    if _locks_dict_lock is None:
        _locks_dict_lock = asyncio.Lock()
    return _locks_dict_lock


async def get_repository_lock(repo_identifier: Union[int, str]) -> asyncio.Lock:
    """
    Get or create a lock for a specific repository.

    Args:
        repo_identifier: Repository ID (int) or path (str)

    Returns:
        asyncio.Lock instance for the repository
    """
    locks_dict_lock = _get_locks_dict_lock()
    async with locks_dict_lock:
        if repo_identifier not in _repository_locks:
            _repository_locks[repo_identifier] = asyncio.Lock()
            logger.debug("Created new lock for repository", repo_id=repo_identifier)
        return _repository_locks[repo_identifier]


P = ParamSpec('P')
T = TypeVar('T')


def with_repository_lock(repo_id_param: str = 'repo_id'):
    """
    Decorator to serialize Borg operations on a per-repository basis.

    This decorator ensures that only one Borg operation runs at a time for each
    repository, preventing lock timeout errors from concurrent access.

    Args:
        repo_id_param: Name of the parameter containing the repository ID
                      (default: 'repo_id')

    Usage:
        @with_repository_lock('repo_id')
        async def my_borg_operation(repo_id: int, ...):
            # This operation will be serialized per repository
            pass
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Extract repository ID from function parameters
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            repo_id = bound_args.arguments.get(repo_id_param)

            if repo_id is None:
                logger.warning(
                    "Repository lock decorator could not find repo_id parameter",
                    function=func.__name__,
                    param=repo_id_param
                )
                # If we can't find the repo_id, just execute without lock
                return await func(*args, **kwargs)

            # Get the lock for this repository
            lock = await get_repository_lock(repo_id)

            # Log when we're waiting for lock
            if lock.locked():
                logger.info(
                    "Waiting for repository lock",
                    repo_id=repo_id,
                    function=func.__name__
                )

            # Execute the function with the lock held
            async with lock:
                logger.debug(
                    "Acquired repository lock",
                    repo_id=repo_id,
                    function=func.__name__
                )
                try:
                    result = await func(*args, **kwargs)
                    logger.debug(
                        "Released repository lock",
                        repo_id=repo_id,
                        function=func.__name__
                    )
                    return result
                except Exception as e:
                    logger.error(
                        "Error during locked operation",
                        repo_id=repo_id,
                        function=func.__name__,
                        error=str(e)
                    )
                    raise

        return wrapper
    return decorator


async def cleanup_unused_locks():
    """
    Remove locks that are not currently held.
    This can be called periodically to prevent memory buildup.
    """
    locks_dict_lock = _get_locks_dict_lock()
    async with locks_dict_lock:
        repo_ids_to_remove = [
            repo_id for repo_id, lock in _repository_locks.items()
            if not lock.locked()
        ]
        for repo_id in repo_ids_to_remove:
            del _repository_locks[repo_id]

        if repo_ids_to_remove:
            logger.debug(
                "Cleaned up unused repository locks",
                count=len(repo_ids_to_remove)
            )
