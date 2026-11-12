"""Notifications read the database off the event loop.

A notification reads its settings, the repository, the timezone and, for an
agent job, the job's plan. Each read on the loop stops every other request
while it runs; only the delivery itself awaits there.
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import event

import app.api.agents as agents
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
from app.services.operations.backup_facade import resolve_backup_job
from tests.utils.operations import seed_job_operation


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
