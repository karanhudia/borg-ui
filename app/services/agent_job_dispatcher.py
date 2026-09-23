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
        # Left queued: the agent's session start and heartbeat send it later.
        logger.info(
            "Agent job left queued: no session for its agent in this process",
            agent_job_id=job.id,
            agent_machine_id=agent_machine_id,
            job_kind=agent_job_kind(job),
        )
        return False
    if job.status != "queued":
        # Cancelled, asked to cancel, or already taken since the caller
        # picked it: a job is sent once, by the pass that moves it off the
        # queue. Two passes can hold the same queued list (a heartbeat and a
        # reconnect of the same agent): after the first send commits, the
        # caller's copy reloads with whatever the other pass wrote.
        return False

    previous_claimed_at = job.claimed_at
    now = _now_utc()
    # Conditional on `queued`: a cancel that took the job off the queue after
    # the caller loaded it wins, as does another pass's claim; nothing is sent.
    claimed = (
        db.query(AgentJob)
        .filter(AgentJob.id == job.id, AgentJob.status == "queued")
        .update(
            {
                AgentJob.status: "claimed",
                AgentJob.claimed_at: now,
                AgentJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    db.refresh(job)
    if not claimed:
        return False

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
        # Back on the queue, unless a cancel landed meanwhile.
        db.query(AgentJob).filter(
            AgentJob.id == job.id, AgentJob.status == "claimed"
        ).update(
            {
                AgentJob.status: "queued",
                AgentJob.claimed_at: previous_claimed_at,
                AgentJob.updated_at: _now_utc(),
            },
            synchronize_session=False,
        )
        db.commit()
        db.refresh(job)
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
        db.rollback()
        reserved_log_keys = {"agent_job_id", "agent_machine_id", "error"}
        safe_context = {
            key: value for key, value in context.items() if key not in reserved_log_keys
        }
        logger.warning(
            "Immediate agent dispatch failed; leaving queued job for fallback handling",
            agent_job_id=getattr(job, "id", None),
            agent_machine_id=getattr(job, "agent_machine_id", None),
            error=str(exc),
            **safe_context,
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
