"""Whether a backup's agent is away (#1331).

A backup on an agent's repository runs on the agent, and its agent job only
reaches the agent over the agent's session. While the agent is away the
backup does nothing but wait, so it must not hold the server-wide backup
slots, and a plan does not start one for it at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.database.models import AgentJob, AgentMachine, Operation, Repository
from app.services.agent_connection_manager import agent_connection_manager

# An agent without a session in this process counts as away only once it has
# also been silent this long. Its session heartbeat stamps `last_seen_at`
# every 30 s, so this is a few missed beats, and a server that has just
# started, before its agents have reconnected, does not take them all for
# away.
AGENT_OFFLINE_GRACE = timedelta(minutes=2)

# `operations.skip_reason` of a backup skipped because its agent was away.
AGENT_OFFLINE_SKIP_REASON = "agent_offline"

# Agent job statuses in which the agent has the job: the backup runs.
_AGENT_HAS_JOB = ("claimed", "running", "cancel_requested")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def agent_is_offline(
    agent: Optional[AgentMachine], *, now: Optional[datetime] = None
) -> bool:
    """True when the agent has no session here and has been silent for
    `AGENT_OFFLINE_GRACE`. An agent that no longer exists is away for good."""
    if agent is None:
        return True
    if agent_connection_manager.is_connected(agent.id):
        return False
    last_seen = agent.last_seen_at or agent.created_at
    if last_seen is None:
        return True
    now = now or datetime.now(timezone.utc)
    return _as_utc(last_seen) <= now - AGENT_OFFLINE_GRACE


def agent_is_gone(agent: Optional[AgentMachine]) -> bool:
    """True for an agent that is not coming back: missing, deleted, revoked
    or disabled. Its backups are refused and reported as failures, never
    skipped as if it were only away."""
    return (
        agent is None
        or agent.deleted_at is not None
        or agent.status in ("disabled", "revoked", "deleted")
    )


def backups_waiting_for_offline_agent(
    db: Session, operation_ids: Iterable[int], *, now: Optional[datetime] = None
) -> set[int]:
    """The agent backups among `operation_ids` that wait for an agent that
    is away: no agent has their job, and the agent it is for is offline.

    A backup for an agent that is connected counts as working from the
    start, before the agent has claimed its job, or every waiting backup
    would start in the same tick of the runner."""
    ids = list(operation_ids)
    if not ids:
        return set()
    rows = (
        db.query(Operation.id, Operation.params, Repository.agent_machine_id)
        .outerjoin(Repository, Repository.id == Operation.repository_id)
        .filter(Operation.id.in_(ids), Operation.kind == "backup")
        .all()
    )
    agent_ids_by_operation = {
        operation_id: agent_machine_id
        for operation_id, params, agent_machine_id in rows
        if isinstance(params, dict) and params.get("executor") == "agent"
    }
    if not agent_ids_by_operation:
        return set()
    # The agent job names the agent the backup went to; the repository names
    # it before the job exists.
    jobs = (
        db.query(AgentJob.operation_id, AgentJob.agent_machine_id, AgentJob.status)
        .filter(AgentJob.operation_id.in_(tuple(agent_ids_by_operation)))
        .order_by(AgentJob.id.asc())
        .all()
    )
    with_agent: set[int] = set()
    for operation_id, agent_machine_id, status in jobs:
        if status in _AGENT_HAS_JOB:
            with_agent.add(operation_id)
        agent_ids_by_operation[operation_id] = agent_machine_id
    agents = {
        agent.id: agent
        for agent in db.query(AgentMachine)
        .filter(
            AgentMachine.id.in_(
                tuple({a for a in agent_ids_by_operation.values() if a is not None})
            )
        )
        .all()
    }
    return {
        operation_id
        for operation_id, agent_machine_id in agent_ids_by_operation.items()
        if operation_id not in with_agent
        and agent_is_offline(agents.get(agent_machine_id), now=now)
    }
