"""A plan's backup waits out read work instead of failing the repository.

The history index runs `repository.diff` as an agent job, which admission
counts as read work on the repository. A plan backup arriving meanwhile
used to be refused with 409 and marked that repository failed. It now
waits for the read work, bounded, and only the refusal that outlives the
budget fails the repository (issue #1102).
"""

import asyncio
import time

import pytest
from fastapi import HTTPException

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation, Repository
from app.services.job_admission import (
    OPERATION_BACKUP,
    READ_WORK_ADMITTED,
    READ_WORK_CANCELLED,
    admit_repository_with_read_work_wait,
)


def _agent_repository(db_session, name: str):
    agent = AgentMachine(
        name=f"agent-{name}",
        agent_id=f"agt_{name}",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
    )
    repo = Repository(
        name=name,
        path=f"/repos/{name}",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=1,
    )
    db_session.add_all([agent, repo])
    db_session.flush()
    repo.agent_machine_id = agent.id
    db_session.commit()
    return agent, repo


def _agent_job(db_session, agent, repo, *, kind="repository.diff"):
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="running",
        payload={
            "schema_version": 1,
            "job_kind": kind,
            "repository": {"id": repo.id, "path": repo.path},
        },
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backup_waits_for_a_running_diff_and_then_runs(db_session):
    agent, repo = _agent_repository(db_session, "diffing")
    job = _agent_job(db_session, agent, repo)

    async def _finish_diff():
        await asyncio.sleep(0.05)
        job.status = "completed"
        db_session.commit()

    finisher = asyncio.ensure_future(_finish_diff())
    outcome = await admit_repository_with_read_work_wait(
        db_session,
        repo,
        OPERATION_BACKUP,
        timeout_seconds=5,
        transient_only=False,
        poll_interval_seconds=0.01,
        retry_pause_seconds=0.0,
    )
    await finisher

    assert outcome == READ_WORK_ADMITTED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_diff_that_outlives_the_budget_still_fails_the_repository(db_session):
    agent, repo = _agent_repository(db_session, "diff-stuck")
    _agent_job(db_session, agent, repo)

    started = time.monotonic()
    with pytest.raises(HTTPException) as refused:
        await admit_repository_with_read_work_wait(
            db_session,
            repo,
            OPERATION_BACKUP,
            timeout_seconds=0.2,
            transient_only=False,
            poll_interval_seconds=0.01,
            retry_pause_seconds=0.0,
        )

    assert refused.value.status_code == 409
    assert refused.value.detail["params"]["active_operation"] == "repository.diff"
    assert time.monotonic() - started >= 0.2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_run_stops_waiting_and_queues_nothing(db_session):
    agent, repo = _agent_repository(db_session, "diff-cancelled")
    _agent_job(db_session, agent, repo)

    assert (
        await admit_repository_with_read_work_wait(
            db_session,
            repo,
            OPERATION_BACKUP,
            timeout_seconds=5,
            transient_only=False,
            poll_interval_seconds=0.01,
            is_cancelled=lambda: True,
        )
        == READ_WORK_CANCELLED
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_write_in_the_way_is_refused_without_waiting(db_session):
    # Another backup or a prune on the repository is not read work: the
    # plan gets the refusal at once, exactly as before.
    agent, repo = _agent_repository(db_session, "pruning")
    db_session.add(
        Operation(
            repository_id=repo.id,
            kind="prune",
            category="maintenance",
            status="running",
            trigger="manual",
            run_id="run-prune-running",
        )
    )
    db_session.commit()

    started = time.monotonic()
    with pytest.raises(HTTPException):
        await admit_repository_with_read_work_wait(
            db_session,
            repo,
            OPERATION_BACKUP,
            timeout_seconds=5,
            transient_only=False,
            poll_interval_seconds=0.01,
        )
    assert time.monotonic() - started < 1
