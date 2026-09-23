"""The stale-job requeue must not overwrite a status committed after its read.

`_requeue_stale_agent_jobs` decides from the status it loaded. A cancel
request or a verdict that commits between that read and the requeue's own
commit is newer than the decision, so the requeue (and the request-scoped
failure next to it) applies only while the row still has the status it was
decided from, and leaves the linked backup operation alone when it did not.
A cancel request that won is settled on the spot: the agent has just shown it
does not run the job, exactly as for a job read as cancel_requested.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.api import agents
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation
from tests.utils.operations import seed_job_operation


def _agent(db):
    agent = AgentMachine(
        name="requeue-agent",
        agent_id="agt_requeue",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    return agent


def _stale_job(db, agent, *, status, payload, operation_id=None):
    stale_at = agents._now_utc() - timedelta(minutes=10)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository" if payload else "backup",
        status=status,
        payload=payload,
        operation_id=operation_id,
        claimed_at=stale_at,
        started_at=stale_at if status == "running" else None,
        created_at=stale_at,
        updated_at=stale_at,
    )
    db.add(job)
    db.commit()
    return job


def _requeue_while_another_session_commits(
    db, agent, job_id, concurrent_status, **requeue_kwargs
):
    """Run the requeue; between its read and its write, a second session
    commits `concurrent_status` for the job. The hook sits on the job-kind
    check, which every requeue and request-scoped failure passes after the
    read (the activity check is skipped for an undelivered job at hello)."""
    real_is_request_scoped = agents._is_request_scoped_repository_job

    def read_then_commit(job):
        if job.id == job_id:
            other = sessionmaker(bind=db.get_bind())()
            try:
                other.query(AgentJob).filter(AgentJob.id == job_id).update(
                    {AgentJob.status: concurrent_status},
                    synchronize_session=False,
                )
                other.commit()
            finally:
                other.close()
        return real_is_request_scoped(job)

    with patch.object(agents, "_is_request_scoped_repository_job", read_then_commit):
        agents._requeue_stale_agent_jobs(
            db,
            agent,
            now=agents._now_utc(),
            running_job_ids=[],
            **requeue_kwargs,
        )
    db.commit()
    db.expire_all()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("concurrent_status", "expected"),
    [
        ("cancel_requested", "canceled"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("canceled", "canceled"),
    ],
)
def test_requeue_keeps_a_status_committed_after_its_read(
    test_db, concurrent_status, expected
):
    agent = _agent(test_db)
    job = _stale_job(
        test_db,
        agent,
        status="running",
        payload={"job_kind": "repository.prune"},
    )

    _requeue_while_another_session_commits(test_db, agent, job.id, concurrent_status)

    assert test_db.get(AgentJob, job.id).status == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("concurrent_status", "expected"),
    [("cancel_requested", "canceled"), ("completed", "completed")],
)
def test_request_scoped_failure_keeps_a_status_committed_after_its_read(
    test_db, concurrent_status, expected
):
    agent = _agent(test_db)
    job = _stale_job(
        test_db,
        agent,
        status="claimed",
        payload={"job_kind": "repository.info"},
    )

    _requeue_while_another_session_commits(test_db, agent, job.id, concurrent_status)

    stored = test_db.get(AgentJob, job.id)
    assert stored.status == expected
    assert stored.error_message is None


@pytest.mark.unit
def test_a_cancel_that_wins_against_the_requeue_cancels_the_backup(test_db):
    agent = _agent(test_db)
    backup = seed_job_operation(test_db, "backup", repository="/repo", status="running")
    test_db.commit()
    job = _stale_job(
        test_db, agent, status="running", payload={}, operation_id=backup.id
    )

    _requeue_while_another_session_commits(test_db, agent, job.id, "cancel_requested")

    assert test_db.get(AgentJob, job.id).status == "canceled"
    assert test_db.get(Operation, backup.id).status == "cancelled"


@pytest.mark.unit
def test_a_verdict_that_wins_against_the_requeue_keeps_the_backup(test_db):
    agent = _agent(test_db)
    backup = seed_job_operation(test_db, "backup", repository="/repo", status="running")
    test_db.commit()
    job = _stale_job(
        test_db, agent, status="running", payload={}, operation_id=backup.id
    )

    _requeue_while_another_session_commits(test_db, agent, job.id, "completed")

    assert test_db.get(AgentJob, job.id).status == "completed"
    assert test_db.get(Operation, backup.id).status == "running"


@pytest.mark.unit
def test_a_cancel_request_wins_on_the_hello_path_too(test_db):
    # At hello the reconnecting session is not registered yet, so the
    # cancel's own dispatch misses it and session heartbeats never return
    # here: settling it now is the only chance before the reaper.
    agent = _agent(test_db)
    job = _stale_job(
        test_db, agent, status="claimed", payload={"job_kind": "repository.prune"}
    )
    _requeue_while_another_session_commits(
        test_db,
        agent,
        job.id,
        "cancel_requested",
        ignore_age_for_undelivered=True,
    )

    assert test_db.get(AgentJob, job.id).status == "canceled"


@pytest.mark.unit
def test_an_unchanged_stale_job_is_still_requeued_with_its_backup(test_db):
    agent = _agent(test_db)
    backup = seed_job_operation(test_db, "backup", repository="/repo", status="running")
    test_db.commit()
    job = _stale_job(
        test_db, agent, status="running", payload={}, operation_id=backup.id
    )

    agents._requeue_stale_agent_jobs(
        test_db, agent, now=agents._now_utc(), running_job_ids=[]
    )
    test_db.commit()
    test_db.expire_all()

    stored = test_db.get(AgentJob, job.id)
    assert stored.status == "queued"
    assert stored.claimed_at is None
    assert stored.started_at is None
    assert test_db.get(Operation, backup.id).status == "queued"
