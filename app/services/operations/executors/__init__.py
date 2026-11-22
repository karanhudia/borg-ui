"""Executor registry: kind -> coroutine taking an OperationContext."""

from typing import TYPE_CHECKING, Awaitable, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.database.models import Operation
    from app.services.operations.runner import OperationContext, Outcome

Executor = Callable[["OperationContext"], Awaitable[Optional["Outcome"]]]
# Whether an agent is doing a running row's work: a live agent job carries
# it, so it goes on without the process that dispatched it.
AgentWork = Callable[["Session", "Operation"], bool]

# The ended rows of a kind whose executor still has work to do: the agent's
# report ended them while no task waited on it.
OwedWork = Callable[["Session"], list["Operation"]]

REGISTRY: dict[str, Executor] = {}
AGENT_WORK: dict[str, AgentWork] = {}
OWED_WORK: dict[str, OwedWork] = {}


def register(
    kind: str,
    executor: Executor,
    *,
    agent_work: Optional[AgentWork] = None,
    owed_work: Optional[OwedWork] = None,
) -> None:
    REGISTRY[kind] = executor
    if agent_work is not None:
        AGENT_WORK[kind] = agent_work
    if owed_work is not None:
        OWED_WORK[kind] = owed_work


def get_executor(kind: str) -> Optional[Executor]:
    return REGISTRY.get(kind)


def registered_kinds() -> set[str]:
    return set(REGISTRY)


def load_default_executors() -> None:
    """Import executor modules for their registration side effect."""
    from app.services.operations.executors import (  # noqa: F401
        backup,
        history,
        index,
        maintenance,
        package,
        prune_compare,
        rclone,
        restore,
        wipe,
    )
