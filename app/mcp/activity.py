"""Activity log and per-connection rate limit (spec 5.11, plan Task 7).

One row per tool call, never with arguments. Rows keep the connection's name
so the history survives revocation. Pruned on write, at most once an hour
per process: there is no single daily job to hook into.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Optional

import structlog

from app.database.models import McpActivity
from app.mcp.context import ConnectionContext
from app.mcp.db import session_scope

logger = structlog.get_logger()

OUTCOMES = ("ok", "error", "denied_level", "denied_rbac")
RATE_LIMIT, RATE_WINDOW_S = 120, 60
RETENTION_DAYS, RETENTION_ROWS = 30, 20_000
PRUNE_EVERY_S = 3600.0
_last_prune = 0.0
# Calls admitted but not yet recorded, per connection. Rows only land when a
# call finishes, so without this a burst of overlapping calls all pass.
# ponytail: per process, fine while gunicorn runs one worker; move to a
# shared counter if that changes.
_in_flight: dict[int, int] = {}


def reserve(conn: ConnectionContext) -> None:
    """Call on the event loop, before allow(): no await in between, so the
    count and the check cannot interleave with another call."""
    _in_flight[conn.connection_id] = _in_flight.get(conn.connection_id, 0) + 1


def release(conn: ConnectionContext) -> None:
    left = _in_flight.get(conn.connection_id, 0) - 1
    if left > 0:
        _in_flight[conn.connection_id] = left
    else:
        _in_flight.pop(conn.connection_id, None)


def allow(app, conn: ConnectionContext) -> bool:
    """True when this call (already reserved) fits in the window."""
    # ponytail: counts rows per call; move to a counter table if the query
    # shows up in profiles.
    running = _in_flight.get(conn.connection_id, 0)
    since = datetime.utcnow() - timedelta(seconds=RATE_WINDOW_S)
    with session_scope(app) as db:
        recent = (
            db.query(McpActivity.id)
            .filter(
                McpActivity.connection_id == conn.connection_id,
                McpActivity.created_at >= since,
            )
            .count()
        )
    return recent + running <= RATE_LIMIT


def _insert(app, conn: ConnectionContext, **fields) -> None:
    with session_scope(app) as db:
        db.add(
            McpActivity(
                connection_id=conn.connection_id,
                connection_name=conn.connection_name,
                user_id=conn.user_id,
                effective_level=conn.level.label,
                created_at=datetime.utcnow(),
                **fields,
            )
        )


def record(
    app,
    conn: ConnectionContext,
    *,
    tool: str,
    outcome: str,
    error_key: Optional[str],
    target: Optional[str],
    duration_ms: int,
) -> None:
    """Never raises into the tool call."""
    global _last_prune
    try:
        _insert(
            app,
            conn,
            tool=tool[:64],
            outcome=outcome,
            error_key=(error_key or None) and error_key[:200],
            target=(target or None) and target[:200],
            duration_ms=max(0, int(duration_ms)),
        )
        if time.monotonic() - _last_prune > PRUNE_EVERY_S:
            _last_prune = time.monotonic()
            prune(app)
    except Exception:
        logger.warning("Failed to record MCP activity", tool=tool, exc_info=True)


def prune(app, *, now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    with session_scope(app) as db:
        removed = (
            db.query(McpActivity)
            .filter(McpActivity.created_at < now - timedelta(days=RETENTION_DAYS))
            .delete(synchronize_session=False)
        )
        cutoff = (
            db.query(McpActivity.id)
            .order_by(McpActivity.created_at.desc(), McpActivity.id.desc())
            .offset(RETENTION_ROWS)
            .limit(1)
            .scalar()
        )
        if cutoff is not None:
            boundary = db.get(McpActivity, cutoff)
            removed += (
                db.query(McpActivity)
                .filter(
                    (McpActivity.created_at < boundary.created_at)
                    | (
                        (McpActivity.created_at == boundary.created_at)
                        & (McpActivity.id <= boundary.id)
                    )
                )
                .delete(synchronize_session=False)
            )
    return removed
