"""Turn failures into one friendly sentence (spec 5.4, plan Task 5).

Never a traceback, never the text of an unexpected exception.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx
import structlog

from app.mcp.client import ApiError
from app.mcp.render import BadCursor, ToolResult
from app.services.error_reporter import report_exception

logger = structlog.get_logger()
STRINGS_FILE = Path(__file__).with_name("backend_strings.json")
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
GENERIC = (
    "Something went wrong inside Borg UI while doing that. Nothing was changed. "
    "The server log has the details."
)


@lru_cache(maxsize=1)
def _strings() -> dict:
    return json.loads(STRINGS_FILE.read_text(encoding="utf-8"))


def backend_message(key: str, params: dict) -> Optional[str]:
    node = _strings()
    for part in key.split(".")[1:]:  # the file is the "backend" subtree
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if not isinstance(node, str):
        return None
    return _PLACEHOLDER.sub(lambda m: str(params.get(m.group(1), m.group(0))), node)


def _label(feature: str) -> str:
    return feature.replace("_", " ").capitalize()


TIMED_OUT = (
    "That took longer than Borg UI waits for an answer here. The work may "
    "still be going on the server. Try again later, or narrow it down (a "
    "smaller path, fewer rules)."
)


def render_error(exc: Exception, *, tool: str) -> ToolResult:
    if isinstance(exc, httpx.TimeoutException):
        logger.warning("MCP tool timed out", tool=tool)
        return ToolResult(TIMED_OUT, is_error=True)
    text = getattr(exc, "text", None)  # resolve.NotFound / Ambiguous, BadCursor
    if isinstance(exc, BadCursor) or (text and not isinstance(exc, ApiError)):
        return ToolResult(text or BadCursor.text, is_error=True)
    if isinstance(exc, ApiError) and exc.key and exc.status >= 500:
        # A keyed server error is a known failure with a translated reason
        # ("failed to list archives"); still logged and reported.
        message = backend_message(exc.key, exc.params)
        if message:
            logger.warning("MCP tool got a server error", tool=tool, key=exc.key)
            report_exception(exc, kind="request", component=f"mcp:{tool}")
            return ToolResult(message, is_error=True)
    if isinstance(exc, ApiError) and exc.status < 500:
        if exc.key and exc.key.startswith("backend.errors.plan."):
            feature = _label(str(exc.params.get("feature", "This feature")))
            required = str(exc.params.get("required", "pro")).capitalize()
            current = str(exc.params.get("current", "community")).capitalize()
            return ToolResult(
                f"{feature} is part of Borg UI {required}. This install is on {current}.",
                is_error=True,
            )
        if exc.key:
            message = backend_message(exc.key, exc.params)
            return ToolResult(
                message or f"Borg UI refused that ({exc.key}).", is_error=True
            )
        if exc.status == 403:
            return ToolResult(
                "Your account does not have permission for that. An admin can change "
                "your role under Settings > Users.",
                is_error=True,
            )
        if exc.status == 404:
            return ToolResult(
                "I could not find that. It may have been removed.", is_error=True
            )
    logger.error("MCP tool failed", tool=tool, exc_info=exc)
    report_exception(exc, kind="request", component=f"mcp:{tool}")
    return ToolResult(GENERIC, is_error=True)


def outcome_for(exc: Exception) -> tuple[str, Optional[str]]:
    if isinstance(exc, ApiError):
        if exc.status == 403 and not (exc.key or "").startswith("backend.errors.plan."):
            return "denied_rbac", exc.key
        return "error", exc.key
    return "error", None
