"""Queued agent jobs of an agent that never comes back (#1176).

A queued job is delivered only over its agent's session (creation push,
session heartbeat, reconnect). An agent that never reconnects leaves the job
queued, and admission control counts it as live work, so the repository stays
blocked until the reaper fails the job.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Repository
import app.services.agent_job_reaper as agent_job_reaper
from app.services.agent_job_reaper import (
    AGENT_OFFLINE_QUEUED_REAP_AFTER,
    reap_queued_jobs_of_offline_agents,
    reap_stale_agent_jobs,
)
from app.services.job_admission import OPERATION_BACKUP, ensure_repository_admission
from tests.utils.operations import seed_job_operation


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _agent_with_repository(db, *, status: str, last_seen_ago: timedelta | None):
    now = datetime.now(timezone.utc)
    agent = AgentMachine(
        name="Agent",
        agent_id="agt_gone",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status=status,
        last_seen_at=_naive(now - last_seen_ago) if last_seen_ago else None,
        created_at=_naive(now - timedelta(days=30)),
    )
    db.add(agent)
    db.flush()
    repo = Repository(
        name="Repo",
        path="/repos/gone-agent",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=agent.id,
    )
    db.add(repo)
    db.flush()
    return agent, repo


def _queued_job(db, agent, repo, *, status="queued", age=timedelta(minutes=1)):
    created = _naive(datetime.now(timezone.utc) - age)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status=status,
        payload={
            "schema_version": 1,
            "job_kind": "repository.info",
            "repository": {"id": repo.id, "path": repo.path},
        },
        created_at=created,
        updated_at=created,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@pytest.mark.unit
def test_queued_job_of_long_offline_agent_is_failed_and_unblocks_repository(
    db_session,
):
    agent, repo = _agent_with_repository(
        db_session, status="offline", last_seen_ago=timedelta(hours=25)
    )
    job = _queued_job(db_session, agent, repo)

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repo, OPERATION_BACKUP)
    assert exc.value.detail["params"]["active_status"] == "queued"

    assert reap_queued_jobs_of_offline_agents(db_session) == 1

    db_session.refresh(job)
    assert job.status == "failed"
    assert job.completed_at is not None
    assert job.error_message == (
        "Reaped by server: no agent activity for over 1440 minutes "
        "(agent offline; job never delivered)."
    )
    ensure_repository_admission(db_session, repo, OPERATION_BACKUP)


@pytest.mark.unit
def test_threshold_runs_from_the_agent_not_from_the_job(db_session):
    # A job created a minute ago for an agent gone for a day has no session to
    # reach it either.
    gone, gone_repo = _agent_with_repository(
        db_session, status="offline", last_seen_ago=timedelta(hours=25)
    )
    fresh_job = _queued_job(db_session, gone, gone_repo, age=timedelta(seconds=5))

    assert reap_queued_jobs_of_offline_agents(db_session) == 1
    db_session.refresh(fresh_job)
    assert fresh_job.status == "failed"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "last_seen_ago"),
    [
        # A laptop asleep overnight keeps its jobs for the reconnect.
        ("offline", AGENT_OFFLINE_QUEUED_REAP_AFTER - timedelta(hours=1)),
        # Connected agent, job older than the threshold: still deliverable.
        ("online", timedelta(seconds=30)),
    ],
)
def test_queued_job_of_recently_seen_agent_is_kept(db_session, status, last_seen_ago):
    agent, repo = _agent_with_repository(
        db_session, status=status, last_seen_ago=last_seen_ago
    )
    job = _queued_job(db_session, agent, repo, age=timedelta(days=2))

    assert reap_queued_jobs_of_offline_agents(db_session) == 0
    db_session.refresh(job)
    assert job.status == "queued"


@pytest.mark.unit
def test_stale_online_status_is_judged_by_last_seen(db_session):
    # A server killed while the agent was connected never writes `offline`;
    # last_seen_at is the signal that survives that.
    agent, repo = _agent_with_repository(
        db_session, status="online", last_seen_ago=timedelta(days=3)
    )
    job = _queued_job(db_session, agent, repo)

    assert reap_queued_jobs_of_offline_agents(db_session) == 1
    db_session.refresh(job)
    assert job.status == "failed"


@pytest.mark.unit
def test_agent_never_seen_falls_back_to_its_creation_time(db_session):
    agent, repo = _agent_with_repository(
        db_session, status="pending", last_seen_ago=None
    )
    job = _queued_job(db_session, agent, repo)

    assert reap_queued_jobs_of_offline_agents(db_session) == 1
    db_session.refresh(job)
    assert job.status == "failed"


@pytest.mark.unit
def test_only_queued_jobs_are_touched(db_session):
    # In-flight jobs stay with the activity-based pass; terminal ones are final.
    agent, repo = _agent_with_repository(
        db_session, status="offline", last_seen_ago=timedelta(hours=25)
    )
    claimed = _queued_job(db_session, agent, repo, status="claimed")
    completed = _queued_job(db_session, agent, repo, status="completed")

    assert reap_queued_jobs_of_offline_agents(db_session) == 0
    db_session.refresh(claimed)
    db_session.refresh(completed)
    assert claimed.status == "claimed"
    assert completed.status == "completed"


@pytest.mark.unit
def test_in_flight_pass_still_skips_queued_jobs(db_session):
    agent, repo = _agent_with_repository(
        db_session, status="offline", last_seen_ago=timedelta(hours=25)
    )
    job = _queued_job(db_session, agent, repo, age=timedelta(hours=2))

    assert reap_stale_agent_jobs(db_session) == 0
    db_session.refresh(job)
    assert job.status == "queued"


@pytest.mark.unit
def test_linked_backup_operation_is_failed_and_reported(db_session):
    agent, repo = _agent_with_repository(
        db_session, status="offline", last_seen_ago=timedelta(hours=25)
    )
    backup = seed_job_operation(
        db_session, "backup", repository=repo.path, status="pending"
    )
    db_session.commit()
    job = _queued_job(db_session, agent, repo)
    job.operation_id = backup.id
    job.updated_at = job.created_at
    db_session.commit()

    failed_backup_job_ids: list[int] = []
    assert (
        reap_queued_jobs_of_offline_agents(
            db_session, failed_backup_job_ids=failed_backup_job_ids
        )
        == 1
    )

    db_session.refresh(backup)
    assert backup.status == "failed"
    assert failed_backup_job_ids == [backup.id]


@pytest.mark.unit
def test_agent_returning_between_read_and_write_keeps_its_job(db_session, monkeypatch):
    agent, repo = _agent_with_repository(
        db_session, status="offline", last_seen_ago=timedelta(hours=25)
    )
    job = _queued_job(db_session, agent, repo)
    agent_id = agent.id

    # The agent's hello commits from its own session after the reaper has
    # read the stale last_seen_at and before it writes.
    original = agent_job_reaper._fail_agent_job

    def reconnect_then_fail(db, *args, **kwargs):
        other = sessionmaker(bind=db_session.get_bind())()
        try:
            now = _naive(datetime.now(timezone.utc))
            other.query(AgentMachine).filter(AgentMachine.id == agent_id).update(
                {"last_seen_at": now, "status": "online"},
                synchronize_session=False,
            )
            other.commit()
        finally:
            other.close()
        return original(db, *args, **kwargs)

    monkeypatch.setattr(agent_job_reaper, "_fail_agent_job", reconnect_then_fail)

    assert reap_queued_jobs_of_offline_agents(db_session) == 0
    db_session.refresh(job)
    assert job.status == "queued"
