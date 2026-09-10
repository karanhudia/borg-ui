"""Dispatching agent self-upgrades, one endpoint at a time and in waves.

The agent is killed by the thing it is reporting on, so a job here records
only that the upgrade was requested; the outcome is resolved by the register
path and the reaper (spec section 7.1). Both the upgrade endpoint and the
agent job reaper dispatch through this module, so there is one dispatcher and
one place that decides how many endpoints may be down at once.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.core.agent_constants import (
    AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS,
    AGENT_UPGRADE_CONCURRENCY,
)
from app.database.models import AgentJob, AgentMachine
from app.services.agent_connection_manager import (
    AgentCommandError,
    AgentCommandTimeout,
    AgentConnectionUnavailable,
    agent_connection_manager,
)

logger = structlog.get_logger()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def request_agent_upgrade(db: Session, agent: AgentMachine, *, target: str):
    """Create the job, dispatch the command, and record the outcome for one
    endpoint. The job is completed at "upgrade started": it records that the
    upgrade was successfully requested, nothing more."""
    now = _now_utc()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="agent_upgrade",
        status="running",
        payload={"target_version": target},
        created_at=now,
        updated_at=now,
        started_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        await agent_connection_manager.send_command(
            agent.id,
            command="agent.upgrade",
            payload={},
            timeout_seconds=AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS,
            wait_for_result=True,
        )
    except (
        AgentConnectionUnavailable,
        AgentCommandTimeout,
        AgentCommandError,
    ) as exc:
        finished = _now_utc()
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = finished
        job.updated_at = finished
        agent.upgrade_state = "failed"
        agent.upgrade_error = str(exc)
        agent.upgrade_target_version = target
        agent.upgrade_requested_at = None
        agent.updated_at = finished
        db.commit()
        return {"agent_machine_id": agent.id, "job_id": job.id, "state": "failed"}

    finished = _now_utc()
    job.status = "completed"
    job.completed_at = finished
    job.updated_at = finished
    agent.upgrade_state = "requested"
    agent.upgrade_requested_at = finished
    agent.upgrade_target_version = target
    agent.upgrade_error = None
    agent.updated_at = finished
    db.commit()
    return {"agent_machine_id": agent.id, "job_id": job.id, "state": "requested"}


async def release_agent_upgrade_waves(db: Session) -> int:
    """Dispatch as many queued upgrades as there are free slots.

    Called both by the upgrade endpoint, so a request under the cap starts at
    once, and by the agent job reaper on every tick, so a slot freed by a
    success or a timeout starts the next endpoint with nobody watching.
    Returns the number dispatched.
    """
    # Counting and claiming happen with no await between them, so the event
    # loop cannot interleave a second release here: the endpoint's inline call
    # and the reaper's tick run on the same loop, and either sees the other's
    # claims committed before it counts. Keep this section await-free, or two
    # releases can each hand out the same free slots and exceed the cap.
    # Ceiling: this holds within one process. A multi-process deployment would
    # need the claim to happen in a single UPDATE against a capacity check.
    in_flight = (
        db.query(AgentMachine).filter(AgentMachine.upgrade_state == "requested").count()
    )
    free = AGENT_UPGRADE_CONCURRENCY - in_flight
    if free <= 0:
        return 0

    waiting = (
        db.query(AgentMachine)
        .filter(AgentMachine.upgrade_state == "queued")
        .order_by(AgentMachine.id)
        .limit(free)
        .all()
    )
    claimed = []
    for agent in waiting:
        # Conditional claim: a row an earlier release already took is skipped
        # rather than dispatched twice.
        if (
            db.query(AgentMachine)
            .filter(
                AgentMachine.id == agent.id,
                AgentMachine.upgrade_state == "queued",
            )
            .update(
                {
                    AgentMachine.upgrade_state: "requested",
                    AgentMachine.upgrade_requested_at: _now_utc(),
                },
                synchronize_session=False,
            )
        ):
            claimed.append(agent)
    db.commit()

    # Dispatch only once every claim is committed, so the slots are already
    # accounted for. Serial on purpose: each send shares this session, which
    # is not safe to use concurrently. Ceiling: a wave of endpoints that are
    # connected but unresponsive costs up to
    # AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS each before the call returns.
    pending = list(claimed)
    dispatched = 0
    try:
        while pending:
            agent = pending[0]
            db.refresh(agent)
            await request_agent_upgrade(db, agent, target=agent.upgrade_target_version)
            pending.pop(0)
            dispatched += 1
    except BaseException:
        # request_agent_upgrade already owns every failure it expects, so
        # reaching here means the wave stopped on something else, cancellation
        # included. The head of pending was attempted and owns its outcome;
        # everything behind it never got a command, and leaving those at
        # "requested" would hold their slots until the reaper's timeout.
        _requeue_undispatched(db, pending[1:])
        raise

    if dispatched:
        logger.info("Agent upgrade wave released", count=dispatched)
    return dispatched


def _requeue_undispatched(db: Session, agents: list[AgentMachine]) -> None:
    """Hand back slots claimed for endpoints nothing was ever sent to."""
    if not agents:
        return
    try:
        for agent in agents:
            db.query(AgentMachine).filter(
                AgentMachine.id == agent.id,
                AgentMachine.upgrade_state == "requested",
            ).update(
                {
                    AgentMachine.upgrade_state: "queued",
                    AgentMachine.upgrade_requested_at: None,
                },
                synchronize_session=False,
            )
        db.commit()
    except Exception:
        # Never mask the failure that got us here. The reaper's timeout still
        # frees these slots, just far later than this would have.
        db.rollback()
        logger.warning(
            "Could not requeue undispatched agent upgrades",
            count=len(agents),
        )
