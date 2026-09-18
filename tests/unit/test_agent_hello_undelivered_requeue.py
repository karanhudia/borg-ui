"""An undelivered claimed job must recover on the very next hello.

_requeue_stale_agent_jobs only requeued a "claimed" job once it had sat idle
past STALE_AGENT_JOB_REQUEUE_AFTER. For a polling agent that is right — its
own claim -> start gap is real work in progress. But a session agent's hello
carries running_job_ids, which is already an authoritative "I don't have this
job": a fresh session cannot have a delivery in flight that predates its own
hello. Without ignoring the age window on that path, a reconnect inside the
window found the stranded job "too fresh" and had no further chance to
recover it until the next disconnect or the reaper, because session
heartbeats are WS messages that never call this function.

ignore_age_for_undelivered=True (passed only from the WS hello call site)
lets an undelivered claimed job (started_at NULL) absent from
running_job_ids requeue regardless of age. Every other job — one the agent
still reports running, or one already started — keeps the age check.
"""

from datetime import timedelta

import pytest

from app.api.agents import (
    STALE_AGENT_JOB_REQUEUE_AFTER,
    _requeue_stale_agent_jobs,
    _now_utc,
)
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine


def _create_agent(db_session):
    agent = AgentMachine(
        name="Hello Agent",
        agent_id="agt_hello",
        token_hash=get_password_hash("secret"),
        token_prefix="secret"[:20],
        status="online",
        capabilities=[],
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def _create_claimed_job(db_session, agent, *, age, started_at=None, job_type="backup"):
    now = _now_utc()
    claimed_at = now - age
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type=job_type,
        status="claimed",
        payload={},
        claimed_at=claimed_at,
        started_at=started_at,
        created_at=claimed_at,
        updated_at=claimed_at,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _create_request_scoped_job(db_session, agent, *, age):
    now = _now_utc()
    claimed_at = now - age
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="claimed",
        payload={"job_kind": "repository.info"},
        claimed_at=claimed_at,
        started_at=None,
        created_at=claimed_at,
        updated_at=claimed_at,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.mark.unit
def test_hello_requeues_young_undelivered_job_absent_from_running_ids(db_session):
    # This is the regression the reviewer flagged: with the 2-minute window,
    # a job stranded seconds before a quick reconnect used to be too fresh to
    # requeue at hello, and hello was the only chance before the reaper.
    agent = _create_agent(db_session)
    job = _create_claimed_job(
        db_session,
        agent,
        age=timedelta(seconds=5),
        started_at=None,
    )
    assert timedelta(seconds=5) < STALE_AGENT_JOB_REQUEUE_AFTER

    _requeue_stale_agent_jobs(
        db_session,
        agent,
        now=_now_utc(),
        running_job_ids=[],
        ignore_age_for_undelivered=True,
    )
    db_session.commit()
    db_session.refresh(job)

    assert job.status == "queued"
    assert job.claimed_at is None
    assert job.started_at is None


@pytest.mark.unit
def test_hello_does_not_requeue_a_job_the_agent_reports_running(db_session):
    # running_job_ids is authoritative in the other direction too: even an
    # undelivered-looking claimed job must not be requeued while the agent
    # says it still has it.
    agent = _create_agent(db_session)
    job = _create_claimed_job(
        db_session,
        agent,
        age=timedelta(seconds=5),
        started_at=None,
    )

    _requeue_stale_agent_jobs(
        db_session,
        agent,
        now=_now_utc(),
        running_job_ids=[job.id],
        ignore_age_for_undelivered=True,
    )
    db_session.commit()
    db_session.refresh(job)

    assert job.status == "claimed"
    assert job.claimed_at is not None


@pytest.mark.unit
def test_heartbeat_path_keeps_the_age_window_for_undelivered_jobs(db_session):
    # The REST /heartbeat path serves polling agents, whose own claim->start
    # gap is real work in progress, not a dropped delivery. The flag defaults
    # to False there, so a young undelivered job must NOT be requeued.
    agent = _create_agent(db_session)
    job = _create_claimed_job(
        db_session,
        agent,
        age=timedelta(seconds=5),
        started_at=None,
    )
    assert timedelta(seconds=5) < STALE_AGENT_JOB_REQUEUE_AFTER

    _requeue_stale_agent_jobs(
        db_session,
        agent,
        now=_now_utc(),
        running_job_ids=[],
    )
    db_session.commit()
    db_session.refresh(job)

    assert job.status == "claimed"
    assert job.claimed_at is not None


@pytest.mark.unit
def test_hello_still_fails_request_scoped_repository_job_terminally(db_session):
    # A request-scoped repository job (e.g. repository.info) has no durable
    # record and no receiver left once the session drops. Even on the hello
    # path with ignore_age_for_undelivered=True, it must be failed terminally
    # rather than requeued.
    agent = _create_agent(db_session)
    job = _create_request_scoped_job(db_session, agent, age=timedelta(seconds=5))

    _requeue_stale_agent_jobs(
        db_session,
        agent,
        now=_now_utc(),
        running_job_ids=[],
        ignore_age_for_undelivered=True,
    )
    db_session.commit()
    db_session.refresh(job)

    assert job.status == "failed"
    assert job.completed_at is not None


@pytest.mark.unit
def test_a_cancel_requested_job_the_agent_no_longer_runs_is_cancelled(test_db):
    """An agent that took the cancel and died before reporting it comes
    back without the job; running it again would undo the cancel."""
    agent = _create_agent(test_db)
    job = _create_claimed_job(
        test_db,
        agent,
        age=STALE_AGENT_JOB_REQUEUE_AFTER + timedelta(minutes=1),
        started_at=_now_utc() - STALE_AGENT_JOB_REQUEUE_AFTER * 2,
        job_type="repository",
    )
    test_db.query(AgentJob).filter(AgentJob.id == job.id).update(
        {AgentJob.status: "cancel_requested", AgentJob.updated_at: job.claimed_at},
        synchronize_session=False,
    )
    test_db.commit()
    test_db.refresh(job)

    _requeue_stale_agent_jobs(test_db, agent, now=_now_utc(), running_job_ids=[])
    test_db.commit()
    test_db.refresh(job)

    assert job.status == "canceled"
    assert job.completed_at is not None


@pytest.mark.unit
def test_a_fresh_cancel_requested_job_is_cancelled_on_hello(test_db):
    """An agent that crashed right after taking the cancel and reconnects at
    once reports no running jobs; its hello settles the cancel without
    waiting out the requeue window."""
    agent = _create_agent(test_db)
    job = _create_claimed_job(
        test_db,
        agent,
        age=timedelta(seconds=5),
        started_at=_now_utc() - timedelta(seconds=5),
        job_type="repository",
    )
    test_db.query(AgentJob).filter(AgentJob.id == job.id).update(
        {AgentJob.status: "cancel_requested"}, synchronize_session=False
    )
    test_db.commit()

    _requeue_stale_agent_jobs(
        test_db,
        agent,
        now=_now_utc(),
        running_job_ids=[],
        ignore_age_for_undelivered=True,
    )
    test_db.commit()
    test_db.refresh(job)

    assert job.status == "canceled"


@pytest.mark.unit
def test_a_fresh_cancel_requested_job_waits_outside_a_hello(test_db):
    """A heartbeat is not authoritative about running jobs: the window holds."""
    agent = _create_agent(test_db)
    job = _create_claimed_job(
        test_db,
        agent,
        age=timedelta(seconds=5),
        started_at=_now_utc() - timedelta(seconds=5),
        job_type="repository",
    )
    test_db.query(AgentJob).filter(AgentJob.id == job.id).update(
        {AgentJob.status: "cancel_requested"}, synchronize_session=False
    )
    test_db.commit()

    _requeue_stale_agent_jobs(test_db, agent, now=_now_utc(), running_job_ids=[])
    test_db.commit()
    test_db.refresh(job)

    assert job.status == "cancel_requested"


@pytest.mark.unit
def test_a_settled_cancel_closes_the_backup_it_carries(test_db):
    """Cancelling the agent job alone would leave its backup running until
    the executor gave up with "returned no result"."""
    from app.database.models import Operation, Repository
    from tests.utils.operations import seed_job_operation

    agent = _create_agent(test_db)
    repo = Repository(
        name="requeue-backup",
        path="/agent/requeue",
        encryption="none",
        compression="lz4",
    )
    test_db.add(repo)
    test_db.commit()
    backup = seed_job_operation(
        test_db,
        "backup",
        repository_id=repo.id,
        status="running",
        started_at=_now_utc(),
        execution_mode="agent",
    )
    test_db.commit()
    job = _create_claimed_job(
        test_db,
        agent,
        age=timedelta(seconds=5),
        started_at=_now_utc() - timedelta(seconds=5),
        job_type="backup",
    )
    test_db.query(AgentJob).filter(AgentJob.id == job.id).update(
        {AgentJob.status: "cancel_requested", AgentJob.operation_id: backup.id},
        synchronize_session=False,
    )
    test_db.commit()

    _requeue_stale_agent_jobs(
        test_db,
        agent,
        now=_now_utc(),
        running_job_ids=[],
        ignore_age_for_undelivered=True,
    )
    test_db.commit()
    test_db.expire_all()

    assert test_db.get(AgentJob, job.id).status == "canceled"
    assert test_db.get(Operation, backup.id).status == "cancelled"
