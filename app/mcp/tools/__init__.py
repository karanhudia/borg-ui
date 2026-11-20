"""Importing this package registers every MCP tool."""

from app.mcp.tools import (  # noqa: F401
    archives,
    connections,
    jobs,
    manage_connections,
    manage_misc,
    manage_plans,
    manage_repositories,
    manage_settings,
    operate,
    overview,
    plans,
    repositories,
    restore,
)
