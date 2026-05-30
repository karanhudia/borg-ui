from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
import structlog

from app.database.models import AgentJob
from app.services.agent_connection_manager import agent_connection_manager

logger = structlog.get_logger()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def agent_job_kind(job: AgentJob) -> str:
    payload = job.payload or {}
    if isinstance(payload, dict):
        payload_kind = payload.get("job_kind")
        if isinstance(payload_kind, str):
            return payload_kind
    return job.job_type


async def dispatch_agent_job_if_connected(
    db: Session,
    job: AgentJob,
    *,
    timeout_seconds: float = 1.0,
) -> bool:
    agent_machine_id = getattr(job, "agent_machine_id", None)
    if agent_machine_id is None:
        return False

    if not agent_connection_manager.is_connected(agent_machine_id):
        return False

    previous_status = job.status
    previous_claimed_at = job.claimed_at
    now = _now_utc()
    if job.status == "queued":
        job.status = "claimed"
        job.claimed_at = now
        job.updated_at = now
        db.commit()

    try:
        await agent_connection_manager.send_command(
            agent_machine_id,
            command=agent_job_kind(job),
            payload=job.payload or {},
            job_id=job.id,
            timeout_seconds=timeout_seconds,
            wait_for_result=False,
        )
    except Exception as exc:
        job.status = previous_status
        job.claimed_at = previous_claimed_at
        job.updated_at = _now_utc()
        db.commit()
        agent_connection_manager.append_log(
            agent_machine_id,
            level="error",
            stream="session",
            job_id=job.id,
            message=f"Failed to dispatch job over session: {exc}",
        )
        return False
    return True


async def dispatch_agent_job_best_effort(
    db: Session,
    job: AgentJob,
    *,
    timeout_seconds: float = 1.0,
    **context: Any,
) -> bool:
    try:
        return await dispatch_agent_job_if_connected(
            db,
            job,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        logger.warning(
            "Immediate agent dispatch failed; leaving queued job for fallback handling",
            agent_job_id=getattr(job, "id", None),
            agent_machine_id=getattr(job, "agent_machine_id", None),
            error=str(exc),
            **context,
        )
        return False


async def dispatch_agent_cancel_if_connected(
    job: AgentJob,
    *,
    timeout_seconds: float = 1.0,
) -> bool:
    if not agent_connection_manager.is_connected(job.agent_machine_id):
        return False

    try:
        await agent_connection_manager.send_command(
            job.agent_machine_id,
            command="cancel",
            payload={"job_id": job.id},
            job_id=job.id,
            timeout_seconds=timeout_seconds,
            wait_for_result=False,
        )
    except Exception as exc:
        agent_connection_manager.append_log(
            job.agent_machine_id,
            level="error",
            stream="session",
            job_id=job.id,
            message=f"Failed to dispatch cancel over session: {exc}",
        )
        return False
    return True
