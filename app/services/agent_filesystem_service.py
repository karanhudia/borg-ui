from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.models import AgentJob, AgentMachine


TERMINAL_AGENT_JOB_STATUSES = {"completed", "failed", "canceled"}


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
    now = _now_utc()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="filesystem",
        status="queued",
        payload={
            "schema_version": 1,
            "job_kind": "filesystem.browse",
            "filesystem": {
                "path": path or "/",
                "include_hidden": include_hidden,
            },
        },
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        db.refresh(job)
        if job.status == "completed":
            return job.result or {}
        if job.status in TERMINAL_AGENT_JOB_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "key": "backend.errors.agents.filesystemBrowseFailed",
                    "message": job.error_message,
                },
            )
        await asyncio.sleep(0.25)

    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail={"key": "backend.errors.agents.filesystemBrowseTimeout"},
    )
