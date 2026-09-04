"""Executor registry: kind -> coroutine taking an OperationContext."""

from typing import TYPE_CHECKING, Awaitable, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover
    from app.services.operations.runner import OperationContext, Outcome

Executor = Callable[["OperationContext"], Awaitable[Optional["Outcome"]]]

REGISTRY: dict[str, Executor] = {}


def register(kind: str, executor: Executor) -> None:
    REGISTRY[kind] = executor


def get_executor(kind: str) -> Optional[Executor]:
    return REGISTRY.get(kind)


def registered_kinds() -> set[str]:
    return set(REGISTRY)


def load_default_executors() -> None:
    """Import executor modules for their registration side effect."""
    from app.services.operations.executors import history, index  # noqa: F401
