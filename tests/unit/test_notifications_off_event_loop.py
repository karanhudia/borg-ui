"""Notifications read the database off the event loop.

A notification reads its settings, the repository, the timezone and, for an
agent job, the job's plan. Each read on the loop stops every other request
while it runs; only the delivery itself awaits there. The reads run through
`run_off_loop`, so a cancelled caller waits for them, and none holds a pooled
connection while a delivery runs.
"""

import asyncio
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

import app.api.agents as agents
from app.database.database import Base
from app.database.models import (
    AgentJob,
    AgentMachine,
    BackupPlan,
    BackupPlanRun,
    NotificationSettings,
    Repository,
)
from app.services.agent_job_notifications import (
    notify_backup_job_finished,
    notify_backup_job_started,
)
from app.services.notification_service import notification_service
from app.services.operations.backup_facade import resolve_backup_job
from tests.utils.operations import seed_job_operation

# Long enough for a thread to get there, short enough that a wait that never
# ends fails the test instead of hanging it.
HOLD_SECONDS = 5


def _on_the_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.fixture
def statements_on_the_loop(test_db):
    recorded = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        if _on_the_loop():
            recorded.append(statement)

    engine = test_db.get_bind()
    event.listen(engine, "before_cursor_execute", on_execute)
    yield recorded
    event.remove(engine, "before_cursor_execute", on_execute)


@pytest.fixture
def apprise():
    with patch("app.services.notification_service.apprise.Apprise") as mock:
        mock.return_value.notify.return_value = True
        yield mock.return_value


def _seed(db, status: str):
    """An agent backup of a plan, to a repository one setting watches."""
    repository = Repository(name="watched", path="/watched")
    db.add(repository)
    setting = NotificationSettings(
        name="Chat",
        service_url="discord://webhook_id/token",
        enabled=True,
        notify_on_backup_start=True,
        notify_on_backup_success=True,
        include_job_name_in_title=True,
        monitor_all_repositories=False,
    )
    setting.repositories.append(repository)
    db.add(setting)
    plan = BackupPlan(name="nightly", source_directories="[]")
    db.add(plan)
    db.commit()
    run = BackupPlanRun(backup_plan_id=plan.id, trigger="manual", status="running")
    db.add(run)
    db.commit()
    operation = seed_job_operation(
        db,
        "backup",
        repository="/watched",
        status=status,
        archive_name="arch-1",
        backup_plan_run_id=run.id,
    )
    agent = AgentMachine(
        name="laptop", agent_id="agt_notify", token_hash="x", token_prefix="x"
    )
    db.add(agent)
    db.commit()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="completed",
        payload={"backup": {"source_paths": ["/home"]}},
        operation_id=operation.id,
    )
    db.add(job)
    db.commit()
    return job, resolve_backup_job(db, operation.id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_backup_start_notification_reads_off_the_loop(
    test_db, apprise, statements_on_the_loop
):
    job, backup_job = _seed(test_db, "running")
    # Committed rows, as the transport hands them over: every read is a query.
    test_db.expire_all()
    statements_on_the_loop.clear()

    await notify_backup_job_started(test_db, job, backup_job)

    assert statements_on_the_loop == []
    assert apprise.notify.call_args.kwargs["title"].endswith("Backup Started - nightly")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_backup_finish_notification_reads_off_the_loop(
    test_db, apprise, statements_on_the_loop
):
    job, _ = _seed(test_db, "completed")
    test_db.expire_all()
    statements_on_the_loop.clear()

    await agents._notify_agent_job_outcome(test_db, job)

    assert statements_on_the_loop == []
    assert "nightly" in apprise.notify.call_args.kwargs["title"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_finish_notification_of_a_backup_job_reads_off_the_loop(
    test_db, apprise, statements_on_the_loop
):
    _, backup_job = _seed(test_db, "completed")
    test_db.expire_all()
    statements_on_the_loop.clear()

    await notify_backup_job_finished(test_db, backup_job)

    assert statements_on_the_loop == []
    assert apprise.notify.call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_notification_waits_for_its_lookup(test_db, monkeypatch):
    """A WebSocket handler cancelled mid-notification cleans up its session in
    `finally`; the lookup still using that session has to finish first."""
    job, _ = _seed(test_db, "completed")
    entered, release = threading.Event(), threading.Event()
    lookups_done = []

    def held_lookup(job, db):
        entered.set()
        release.wait(HOLD_SECONDS)
        lookups_done.append(True)
        return None, None

    monkeypatch.setattr(agents, "_jobs_to_notify_for", held_lookup)
    task = asyncio.ensure_future(agents._notify_agent_job_outcome(test_db, job))
    assert await asyncio.to_thread(entered.wait, HOLD_SECONDS)

    task.cancel()
    await asyncio.sleep(0.1)
    still_waiting = not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert still_waiting
    assert lookups_done == [True]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_burst_of_slow_deliveries_holds_no_connection(tmp_path, apprise):
    """More notifications than the pool has connections, each delivery waiting
    for the others: a session that kept its connection through its delivery
    would leave the rest waiting for a checkout until the pool timeout."""
    burst = 3
    engine = create_engine(
        f"sqlite:///{tmp_path / 'burst.db'}",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=HOLD_SECONDS,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with sessions() as db:
        db.add(
            NotificationSettings(
                name="Chat",
                service_url="discord://webhook_id/token",
                enabled=True,
                notify_on_backup_start=True,
                monitor_all_repositories=True,
            )
        )
        db.commit()

    together = threading.Barrier(burst, timeout=HOLD_SECONDS)
    delivered = []

    def notify(**kwargs):
        together.wait()
        delivered.append(kwargs["title"])
        return True

    apprise.notify.side_effect = notify
    burst_sessions = [sessions() for _ in range(burst)]
    try:
        await asyncio.gather(
            *(
                notification_service.send_backup_start(db, "repo", f"archive-{i}")
                for i, db in enumerate(burst_sessions)
            )
        )
    finally:
        for db in burst_sessions:
            db.close()
        engine.dispose()

    assert len(delivered) == burst


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_notification_called_with_db_by_keyword_is_sent(test_db, apprise):
    """The check services and the agent check path pass `db=` by keyword."""
    test_db.add(
        NotificationSettings(
            name="Chat",
            service_url="discord://webhook_id/token",
            enabled=True,
            notify_on_check_success=True,
            monitor_all_repositories=True,
        )
    )
    test_db.commit()

    await notification_service.send_check_completion(
        db=test_db,
        repository_name="repo",
        repository_path="/repo",
        status="completed",
    )

    assert apprise.notify.call_count == 1
