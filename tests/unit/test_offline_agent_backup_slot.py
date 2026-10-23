"""A backup for an agent that is away does not hold the backup slots (#1331).

The work of an agent backup runs on the agent. While its agent job waits for
an agent that has no session, the backup does nothing, and counting it
against `max_concurrent_backups` (default 1) stopped every other backup on
the server until the reaper ended the job a day later.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentMachine,
    Repository,
    ScheduledJob,
    SystemSettings,
)
from app.services.agent_connection_manager import agent_connection_manager
from app.services.job_admission import (
    count_active_manual_backup_jobs,
    count_active_scheduled_backup_jobs,
)
from app.services.operations import lanes
from app.services.operations.enqueue import enqueue


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def connected(monkeypatch):
    """The agent ids that have a session in this process."""
    ids: set[int] = set()
    monkeypatch.setattr(
        agent_connection_manager, "is_connected", lambda agent_id: agent_id in ids
    )
    return ids


def _agent(db, name, *, last_seen_ago):
    agent = AgentMachine(
        name=name,
        agent_id=f"agt_{name}",
        token_hash=get_password_hash("agent-secret"),
        token_prefix=f"secret-{name}",
        status="offline",
        last_seen_at=_naive(datetime.now(timezone.utc) - last_seen_ago),
        created_at=_naive(datetime.now(timezone.utc) - timedelta(days=30)),
    )
    db.add(agent)
    db.flush()
    return agent


def _agent_repository(db, agent, name):
    repo = Repository(
        name=name,
        path=f"/repos/{name}",
        encryption="none",
        compression="lz4",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=agent.id,
    )
    db.add(repo)
    db.commit()
    return repo


def _backup(db, repo, *, trigger="plan", status="queued", agent_job_status=None):
    op = enqueue(
        db,
        "backup",
        repository_id=repo.id,
        trigger=trigger,
        params={"executor": "agent"},
    )
    op.status = status
    if agent_job_status is not None:
        db.add(
            AgentJob(
                agent_machine_id=repo.agent_machine_id,
                operation_id=op.id,
                job_type="backup",
                status=agent_job_status,
                payload={"job_kind": "backup.create"},
            )
        )
    db.commit()
    return op


@pytest.fixture()
def settings(db_session):
    s = SystemSettings(max_concurrent_backups=1, max_concurrent_scheduled_backups=1)
    db_session.add(s)
    db_session.commit()
    return s


@pytest.mark.unit
@pytest.mark.parametrize("trigger", ["plan", "manual", "schedule"])
def test_backup_waiting_for_an_offline_agent_leaves_the_slot_free(
    db_session, settings, connected, trigger
):
    away = _agent(db_session, "laptop", last_seen_ago=timedelta(minutes=50))
    online = _agent(db_session, "server", last_seen_ago=timedelta(seconds=10))
    connected.add(online.id)
    _backup(
        db_session,
        _agent_repository(db_session, away, "laptop"),
        trigger=trigger,
        status="running",
        agent_job_status="queued",
    )
    waiting = _backup(
        db_session, _agent_repository(db_session, online, "server"), trigger=trigger
    )

    assert lanes.can_start(db_session, waiting, settings) is True


@pytest.mark.unit
def test_backup_whose_agent_has_no_job_yet_leaves_the_slot_free(
    db_session, settings, connected
):
    """Before its agent job exists (the repository's pre-backup hooks, which
    are agent jobs too), a backup for an agent that is away waits as well."""
    away = _agent(db_session, "laptop", last_seen_ago=timedelta(minutes=50))
    online = _agent(db_session, "server", last_seen_ago=timedelta(seconds=10))
    connected.add(online.id)
    _backup(db_session, _agent_repository(db_session, away, "laptop"), status="running")
    waiting = _backup(db_session, _agent_repository(db_session, online, "server"))

    assert lanes.can_start(db_session, waiting, settings) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("agent_job_status", "agent_connected", "last_seen_ago"),
    [
        # the agent has the job and runs the backup, session or not
        ("claimed", False, timedelta(minutes=50)),
        ("running", False, timedelta(minutes=50)),
        ("cancel_requested", False, timedelta(minutes=50)),
        # connected: claimed within moments, so it counts from the start
        ("queued", True, timedelta(seconds=10)),
        (None, True, timedelta(seconds=10)),
        # no session, but seen just now: a server that has just started
        # before its agents reconnected
        ("queued", False, timedelta(seconds=30)),
    ],
)
def test_backup_with_its_agent_holds_the_slot(
    db_session, settings, connected, agent_job_status, agent_connected, last_seen_ago
):
    agent = _agent(db_session, "busy", last_seen_ago=last_seen_ago)
    if agent_connected:
        connected.add(agent.id)
    _backup(
        db_session,
        _agent_repository(db_session, agent, "busy"),
        status="running",
        agent_job_status=agent_job_status,
    )
    other = _agent(db_session, "other", last_seen_ago=timedelta(seconds=10))
    connected.add(other.id)
    waiting = _backup(db_session, _agent_repository(db_session, other, "other"))

    assert lanes.can_start(db_session, waiting, settings) is False


@pytest.mark.unit
def test_server_backups_still_hold_the_slot(db_session, settings, connected):
    server_repo = Repository(
        name="local", path="/repos/local", encryption="none", compression="lz4"
    )
    db_session.add(server_repo)
    db_session.commit()
    op = enqueue(
        db_session,
        "backup",
        repository_id=server_repo.id,
        params={"executor": "server"},
    )
    op.status = "running"
    db_session.commit()
    other = _agent(db_session, "other", last_seen_ago=timedelta(seconds=10))
    connected.add(other.id)
    waiting = _backup(db_session, _agent_repository(db_session, other, "other"))

    assert lanes.can_start(db_session, waiting, settings) is False


@pytest.mark.unit
def test_admission_counts_skip_backups_waiting_for_an_offline_agent(
    db_session, connected
):
    away = _agent(db_session, "laptop", last_seen_ago=timedelta(minutes=50))
    repo = _agent_repository(db_session, away, "laptop")
    _backup(
        db_session, repo, trigger="manual", status="running", agent_job_status="queued"
    )
    _backup(db_session, repo, trigger="manual", status="queued")
    schedule = ScheduledJob(name="hourly", cron_expression="0 * * * *")
    db_session.add(schedule)
    db_session.commit()
    scheduled = _backup(db_session, repo, trigger="schedule", status="running")
    scheduled.scheduled_job_id = schedule.id
    db_session.commit()

    assert count_active_manual_backup_jobs(db_session) == 0
    assert count_active_scheduled_backup_jobs(db_session) == 0
    connected.add(away.id)
    assert count_active_manual_backup_jobs(db_session) == 2
    assert count_active_scheduled_backup_jobs(db_session) == 1
