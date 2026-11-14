"""Result shaping for MCP tools: units, paging and the size cap (spec 5.7, 5.8).

Every result leaves through `finish`, the one place that redacts and caps.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import mcp.types as types

from app.mcp.redact import scrub
from app.utils.redaction import redact_secrets

LIST_DEFAULT, LIST_MAX = 25, 200
LOG_DEFAULT, LOG_MAX = 200, 1000
RESULT_CAP = 60_000
SHORTENED = "Output was shortened to fit. Ask for a smaller page or a narrower path."


@dataclass
class ToolResult:
    text: str  # markdown, outcome first (app/mcp/STYLE.md)
    data: dict = field(default_factory=dict)  # becomes structured_content
    is_error: bool = False


class BadCursor(ValueError):
    text = (
        "That page marker is not valid anymore. Ask for the list again from the start."
    )


def human_size(n: Optional[int]) -> str:
    if n is None:
        return "unknown"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "PB":
            break
        size /= 1024
    else:
        unit = "PB"
    if unit == "B":
        return f"{int(size)} B"
    return f"{size:.1f} {unit}"


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)  # the app stores naive UTC
    return value.astimezone(timezone.utc)


def _ago(seconds: float) -> str:
    future = seconds < 0
    seconds = abs(seconds)
    if seconds < 60:
        return "just now"
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            count = int(seconds // size)
            label = f"{count} {unit}{'' if count == 1 else 's'}"
            return f"in {label}" if future else f"{label} ago"
    return "just now"


def ago(value: datetime | str | None) -> str:
    """Short relative time for list lines: "3 hours ago", "never"."""
    if not value:
        return "never"
    return _ago((datetime.now(timezone.utc) - _as_utc(value)).total_seconds())


def when(value: datetime | str | None) -> str:
    if not value:
        return "never"
    moment = _as_utc(value)
    seconds = (datetime.now(timezone.utc) - moment).total_seconds()
    return f"{_ago(seconds)} ({moment:%Y-%m-%d %H:%M} UTC)"


def duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60} min"


def clamp_limit(
    limit: Optional[int], default: int = LIST_DEFAULT, max_: int = LIST_MAX
) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), max_))


def _encode(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()


def decode_cursor(cursor: Optional[str]) -> int:
    if not cursor:
        return 0
    try:
        offset = json.loads(base64.urlsafe_b64decode(cursor.encode()))["o"]
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise BadCursor() from None
    if not isinstance(offset, int) or offset < 0:
        raise BadCursor()
    return offset


def page(items: list, limit: int, cursor: Optional[str]) -> tuple[list, Optional[str]]:
    offset = decode_cursor(cursor)
    chunk = items[offset : offset + limit]
    end = offset + len(chunk)
    return chunk, (_encode(end) if end < len(items) else None)


def next_cursor(offset: int) -> str:
    return _encode(offset)


def more_line(
    shown: int, total: Optional[int], noun: str, next_cursor: Optional[str]
) -> str:
    if not next_cursor:
        return ""
    of = f" of {total}" if total is not None else ""
    return f"Showing {shown}{of} {noun}. Ask for the next page to see more."


def _cap_text(text: str) -> str:
    if len(text) <= RESULT_CAP:
        return text
    room = RESULT_CAP - len(SHORTENED) - 2
    cut = text[:room]
    if "\n" in cut:
        cut = cut[: cut.rfind("\n")]
    return f"{cut}\n\n{SHORTENED}"


def _longest_list(value: Any) -> Optional[list]:
    best: Optional[list] = None
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            if best is None or len(item) > len(best):
                best = item
            stack.extend(item)
    return best


def _cap_data(data: dict) -> dict:
    if len(json.dumps(data, default=str)) <= RESULT_CAP:
        return data
    data = json.loads(json.dumps(data, default=str))
    data["truncated"] = True
    while len(json.dumps(data)) > RESULT_CAP:
        longest = _longest_list(data)
        if not longest:
            return {"truncated": True}
        del longest[len(longest) // 2 :]
    return data


def finish(result: ToolResult) -> types.CallToolResult:
    text = _cap_text(redact_secrets(result.text) or "")
    data = _cap_data(scrub(result.data)) if result.data else None
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structured_content=data,
        is_error=result.is_error,
    )
