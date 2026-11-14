"""Authenticate an MCP connection token (spec 2026-11-14-mcp-server, 5.2).

Only `kind == "mcp"` rows match, so personal tokens and login JWTs are
refused at /mcp. A process cache skips bcrypt for 60 s per token, but every
call still loads the row and the user by primary key, so a revoked
connection or a deactivated user is refused on the very next call.
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional

from anyio import to_thread

from app.core.security import API_TOKEN_PREFIX, API_TOKEN_PREFIX_LENGTH, verify_password
from app.database.models import ApiToken, User
from app.mcp.context import ConnectionContext
from app.mcp.db import session_scope
from app.mcp.levels import effective_level
from app.utils.datetime_utils import utc_now

CACHE_SECONDS = 60.0
_cache: dict[str, tuple[int, float]] = {}  # sha256(token) -> (connection id, expiry)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _find(db, token: str) -> Optional[ApiToken]:
    digest = _digest(token)
    cached = _cache.get(digest)
    if cached and cached[1] > time.monotonic():
        return db.get(ApiToken, cached[0])
    candidates = (
        db.query(ApiToken)
        .filter(
            ApiToken.prefix == token[:API_TOKEN_PREFIX_LENGTH], ApiToken.kind == "mcp"
        )
        .all()
    )
    for row in candidates:
        if verify_password(token, row.token_hash):
            _cache[digest] = (row.id, time.monotonic() + CACHE_SECONDS)
            return row
    return None


def _authenticate(app, token: str) -> Optional[ConnectionContext]:
    from app.api.mcp_connections import mcp_settings

    with session_scope(app) as db:
        row = _find(db, token)
        if row is None or row.kind != "mcp":
            return None
        user = db.get(User, row.user_id)
        if user is None or not user.is_active:
            return None
        cap = mcp_settings(db).mcp_max_access_level
        row.last_used_at = utc_now()
        return ConnectionContext(
            connection_id=row.id,
            connection_name=row.name,
            user_id=user.id,
            username=user.username,
            level=effective_level(row.access_level, cap),
        )


async def authenticate(app, token: str) -> Optional[ConnectionContext]:
    if not token.startswith(API_TOKEN_PREFIX):
        return None
    return await to_thread.run_sync(_authenticate, app, token)


def save_client_info(app, connection_id: int, name: str, version: str) -> None:
    with session_scope(app) as db:
        row = db.get(ApiToken, connection_id)
        if row is not None:
            row.last_client_name = name[:100] or None
            row.last_client_version = version[:100] or None


def clear_cache() -> None:
    _cache.clear()
