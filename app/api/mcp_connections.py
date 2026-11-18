"""MCP connections, the admin switch and the level cap.

Spec 2026-11-14-mcp-server, 5.2. A connection is an `api_tokens` row with
kind "mcp"; its token is shown once, at creation, like a personal token.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.features import require_feature
from app.core.security import (
    API_TOKEN_PREFIX,
    get_current_admin_user,
    get_current_user,
    get_password_hash,
    refuse_mcp_internal,
)
from app.database.database import get_db
from app.database.models import ApiToken, McpActivity, SystemSettings, User
from app.mcp.levels import LEVEL_NAMES, Level, effective_level
from app.mcp.registry import top_level
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()

router = APIRouter(
    prefix="/settings/mcp",
    tags=["MCP"],
    dependencies=[require_feature("mcp"), Depends(refuse_mcp_internal)],
)


def _error(status_code: int, key: str, **params) -> HTTPException:
    detail = {"key": key, "params": params} if params else {"key": key}
    return HTTPException(status_code=status_code, detail=detail)


def _level_name(value: str) -> str:
    if value not in LEVEL_NAMES:
        raise ValueError(f"access_level must be one of {', '.join(LEVEL_NAMES)}")
    return value


class ConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    max_access_level: Optional[str] = None

    _check_level = field_validator("max_access_level")(
        lambda cls, v: v if v is None else _level_name(v)
    )


class ConnectionCreate(BaseModel):
    name: str
    access_level: str
    skip_routine_confirmations: bool = False

    _check_level = field_validator("access_level")(lambda cls, v: _level_name(v))


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    access_level: Optional[str] = None
    skip_routine_confirmations: Optional[bool] = None

    _check_level = field_validator("access_level")(
        lambda cls, v: v if v is None else _level_name(v)
    )


def mcp_settings(db: Session) -> SystemSettings:
    """The settings row, created with defaults when an install has none."""
    settings = db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _config(settings: SystemSettings, request: Request) -> dict:
    root = request.scope.get("root_path", "") or ""
    return {
        "enabled": bool(settings.mcp_enabled),
        "max_access_level": settings.mcp_max_access_level,
        "endpoint_path": f"{root}/mcp",
        "available_levels": [n for n in LEVEL_NAMES if Level.parse(n) <= top_level()],
    }


def _utc_midnight() -> datetime:
    # ponytail: "today" is the UTC day; per-user time zones if anyone asks.
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )


def _calls_today(db: Session, connection_ids: list[int]) -> dict[int, int]:
    midnight = _utc_midnight()
    if not connection_ids:
        return {}
    rows = (
        db.query(McpActivity.connection_id, func.count(McpActivity.id))
        .filter(
            McpActivity.connection_id.in_(connection_ids),
            McpActivity.created_at >= midnight,
        )
        .group_by(McpActivity.connection_id)
        .all()
    )
    return dict(rows)


def _row(
    token: ApiToken,
    cap: str,
    username: Optional[str] = None,
    calls_today: int = 0,
) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.prefix,
        "access_level": token.access_level,
        "effective_level": effective_level(token.access_level, cap).label,
        "skip_routine_confirmations": bool(token.skip_routine_confirmations),
        "last_client_name": token.last_client_name,
        "last_client_version": token.last_client_version,
        "last_used_at": serialize_datetime(token.last_used_at),
        "created_at": serialize_datetime(token.created_at),
        "username": username,
        "calls_today": calls_today,
    }


def _check_rules(
    level: str, skip: bool, cap: str, *, setting_level: bool = True
) -> None:
    # Only a level being set must have tools; a stored one is left alone.
    if setting_level and Level.parse(level) > top_level():
        raise _error(422, "backend.errors.mcp.levelNotAvailable", level=level)
    if Level.parse(level) > Level.parse(cap):
        raise _error(422, "backend.errors.mcp.levelAboveCap", max=cap)
    if skip and Level.parse(level) != Level.FULL:
        raise _error(422, "backend.errors.mcp.skipNeedsFull")


def _owned(db: Session, connection_id: int, user: User) -> ApiToken:
    """The connection if this user may manage it; 404 otherwise, never 403,
    so other users' connection ids are not confirmed."""
    query = db.query(ApiToken).filter(
        ApiToken.id == connection_id, ApiToken.kind == "mcp"
    )
    if user.role != "admin":
        query = query.filter(ApiToken.user_id == user.id)
    token = query.first()
    if token is None:
        raise _error(404, "backend.errors.mcp.connectionNotFound")
    return token


@router.get("/config")
def get_config(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _config(mcp_settings(db), request)


@router.put("/config")
def update_config(
    payload: ConfigUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    settings = mcp_settings(db)
    if payload.enabled is not None:
        settings.mcp_enabled = payload.enabled
    if payload.max_access_level is not None:
        settings.mcp_max_access_level = payload.max_access_level
    db.commit()
    logger.info(
        "MCP config updated",
        user=current_user.username,
        enabled=settings.mcp_enabled,
        max_access_level=settings.mcp_max_access_level,
    )
    return _config(settings, request)


@router.get("/connections")
def list_connections(
    all: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if all and current_user.role != "admin":
        raise _error(403, "backend.errors.auth.notEnoughPermissions")
    cap = mcp_settings(db).mcp_max_access_level
    query = (
        db.query(ApiToken, User.username)
        .join(User, User.id == ApiToken.user_id)
        .filter(ApiToken.kind == "mcp")
    )
    if not all:
        query = query.filter(ApiToken.user_id == current_user.id)
    rows = query.order_by(ApiToken.created_at.desc()).all()
    calls = _calls_today(db, [token.id for token, _ in rows])
    return [
        _row(token, cap, username, calls.get(token.id, 0)) for token, username in rows
    ]


@router.post("/connections", status_code=201)
def create_connection(
    payload: ConnectionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise _error(422, "backend.errors.mcp.nameRequired")
    cap = mcp_settings(db).mcp_max_access_level
    _check_rules(payload.access_level, payload.skip_routine_confirmations, cap)

    raw_token = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=current_user.id,
        name=name,
        token_hash=get_password_hash(raw_token),
        prefix=raw_token[:12],
        created_at=datetime.now(timezone.utc),
        kind="mcp",
        access_level=payload.access_level,
        skip_routine_confirmations=payload.skip_routine_confirmations,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    logger.info(
        "MCP connection created",
        user=current_user.username,
        connection_id=token.id,
        access_level=token.access_level,
    )
    return {**_row(token, cap, current_user.username), "token": raw_token}


@router.patch("/connections/{connection_id}")
def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = _owned(db, connection_id, current_user)
    cap = mcp_settings(db).mcp_max_access_level
    if payload.name is not None:
        if not payload.name.strip():
            raise _error(422, "backend.errors.mcp.nameRequired")
        token.name = payload.name.strip()
    level = payload.access_level or token.access_level
    if payload.skip_routine_confirmations is not None:
        skip = payload.skip_routine_confirmations
    else:
        # Leaving Full drops the confirmation shortcut with it.
        skip = bool(token.skip_routine_confirmations) and (
            Level.parse(level) == Level.FULL
        )
    if payload.access_level is not None or payload.skip_routine_confirmations:
        _check_rules(level, skip, cap, setting_level=payload.access_level is not None)
    token.access_level = level
    token.skip_routine_confirmations = skip
    calls = _calls_today(db, [token.id]).get(token.id, 0)
    db.commit()
    db.refresh(token)
    logger.info(
        "MCP connection updated",
        user=current_user.username,
        connection_id=token.id,
        access_level=token.access_level,
    )
    owner = db.query(User.username).filter(User.id == token.user_id).scalar()
    return _row(token, cap, owner, calls)


@router.delete("/connections/{connection_id}", status_code=204)
def delete_connection(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = _owned(db, connection_id, current_user)
    db.delete(token)
    db.commit()
    logger.info(
        "MCP connection revoked",
        user=current_user.username,
        connection_id=connection_id,
    )


@router.get("/connections/{connection_id}/activity")
def list_activity(
    connection_id: int,
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned(db, connection_id, current_user)
    query = db.query(McpActivity).filter(McpActivity.connection_id == connection_id)
    if before_id is not None:
        # Ids grow with time and never tie, so a page boundary drops nothing.
        query = query.filter(McpActivity.id < before_id)
    rows = query.order_by(McpActivity.id.desc()).limit(limit)
    return [
        {
            "id": row.id,
            "tool": row.tool,
            "effective_level": row.effective_level,
            "outcome": row.outcome,
            "error_key": row.error_key,
            "target": row.target,
            "duration_ms": row.duration_ms,
            "created_at": serialize_datetime(row.created_at),
        }
        for row in rows
    ]
