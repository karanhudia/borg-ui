"""Per-call context handed to MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.mcp.client import InternalClient
from app.mcp.levels import Level


@dataclass(frozen=True)
class ConnectionContext:
    connection_id: int
    connection_name: str
    user_id: int
    username: str
    level: Level  # effective: min(connection level, admin cap)


@dataclass
class ToolContext:
    conn: ConnectionContext
    api: InternalClient
    target: Optional[str] = None  # set by resolvers, kept in the activity log
