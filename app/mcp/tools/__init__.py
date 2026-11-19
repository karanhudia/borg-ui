"""Importing this package registers every MCP tool."""

from app.mcp.tools import (  # noqa: F401
    archives,
    connections,
    jobs,
    operate,
    overview,
    plans,
    repositories,
    restore,
)
