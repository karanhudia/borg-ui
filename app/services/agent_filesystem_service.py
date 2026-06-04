from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.agent_constants import AGENT_FILESYSTEM_BROWSE_MAX_ITEMS
from app.database.models import AgentMachine
from app.services.agent_connection_manager import (
    AgentCommandError,
    AgentCommandTimeout,
    AgentConnectionUnavailable,
    agent_connection_manager,
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _require_browse_agent(db: Session, agent_machine_id: int) -> AgentMachine:
    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )
    if agent.status != "online":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.agentOffline"},
        )
    capabilities = agent.capabilities or []
    if "filesystem.browse" not in capabilities:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.capabilityMissing"},
        )
    return agent


async def browse_agent_filesystem(
    db: Session,
    agent_machine_id: int,
    *,
    path: str,
    include_hidden: bool = False,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    agent = _require_browse_agent(db, agent_machine_id)
    try:
        result = await agent_connection_manager.send_command(
            agent.id,
            command="filesystem.browse",
            payload={
                "path": path or "/",
                "include_hidden": include_hidden,
                "max_items": AGENT_FILESYSTEM_BROWSE_MAX_ITEMS,
            },
            timeout_seconds=timeout_seconds,
            wait_for_result=True,
        )
    except AgentConnectionUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"key": "backend.errors.agents.agentOffline"},
        ) from exc
    except AgentCommandTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"key": "backend.errors.agents.filesystemBrowseTimeout"},
        ) from exc
    except AgentCommandError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "key": "backend.errors.agents.filesystemBrowseFailed",
                "message": str(exc),
            },
        ) from exc

    if result.get("success") is False:
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "key": "backend.errors.agents.filesystemBrowseFailed",
                "message": error.get("message") or "Filesystem browse failed",
            },
        )

    items = result.get("items")
    if isinstance(items, list) and len(items) > AGENT_FILESYSTEM_BROWSE_MAX_ITEMS:
        result = {
            **result,
            "items": items[:AGENT_FILESYSTEM_BROWSE_MAX_ITEMS],
            "items_truncated": True,
        }
    else:
        result.setdefault("items_truncated", False)

    return result
