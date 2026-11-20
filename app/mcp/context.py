"""Per-call context handed to MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from app.mcp.client import InternalClient
from app.mcp.levels import Level


@dataclass(frozen=True)
class ConnectionContext:
    connection_id: int
    connection_name: str
    user_id: int
    username: str
    level: Level  # effective: min(connection level, admin cap)


async def _no_progress(percent: float, message: Optional[str] = None) -> None:
    return None


@dataclass
class ToolContext:
    conn: ConnectionContext
    api: InternalClient
    target: Optional[str] = None  # set by resolvers, kept in the activity log
    # Reports a percentage and a message on the call's own answer stream; a
    # no-op when the client sent no progressToken (spec 5.8).
    progress: Callable[[float, Optional[str]], Awaitable[None]] = _no_progress
    # Where the user opens the web UI, for hand-off links (spec 5.9).
    base_url: str = ""
