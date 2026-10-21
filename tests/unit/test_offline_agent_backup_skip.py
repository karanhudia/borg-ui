"""A backup for an agent that is away is skipped, not queued (#1331).

A plan does not start a backup for a repository whose agent has no session,
and a backup queued before its agent went away waits no longer than its
plan's next run, at most four hours. Either way the backup ends `skipped`
("agent offline") without a notification: an agent away on purpose (a
laptop) misses runs as a matter of course, and a repository left without a
backup for long is what the stale-backup monitoring reports.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentMachine,
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    BackupPlanRunRepository,
    Operation,
    Repository,
)
from app.services.agent_connection_manager import agent_connection_manager
from app.services.backup_plan_execution_service import backup_plan_execution_service


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _ago(delta: timedelta) -> datetime:
    return _naive(datetime.now(timezone.utc) - delta)


@pytest.fixture()
def connected(monkeypatch):
    ids: set[int] = set()
    monkeypatch.setattr(
        agent_connection_manager, "is_connected", lambda agent_id: agent_id in ids
    )
    return ids


@pytest.fixture()
def failure_notifications():
    from app.services.notification_service import notification_service

    with patch.object(
        notification_service, "send_backup_failure", new_callable=AsyncMock
    ) as sent:
        yield sent


def _agent(db, name, *, last_seen_ago):
    agent = AgentMachine(
        name=name,
        agent_id=f"agt_{name}",
        token_hash=get_password_hash("agent-secret"),
        token_prefix=f"secret-{name}",
        status="offline",
        last_seen_at=_ago(last_seen_ago),
        created_at=_ago(timedelta(days=30)),
    )
    db.add(agent)
    db.commit()
    return agent


def _repo(db, name, agent=None):
    repo = Repository(
        name=name,
        path=f"/repos/{name}",
        encryption="none",
        repository_type="local",
        mode="full",
        executor_type="agent" if agent is not None else None,
        execution_target="local",
        agent_machine_id=agent.id if agent is not None else None,
    )
    db.add(repo)
    db.commit()
    return repo


def _plan(db, repos, **overrides):
    values = {
        "name": "Hourly",
        "enabled": True,
        "source_type": "agent",
        "source_directories": json.dumps(["/home"]),
        # each agent backs up its own machine
        "source_locations": json.dumps(
            [
                {
                    "source_type": "agent",
                    "source_ssh_connection_id": None,
                    "agent_machine_id": agent_id,
                    "paths": ["/home"],
                }
                for agent_id in sorted(
                    {repo.agent_machine_id for repo in repos if repo.agent_machine_id}
                )
            ]
        ),
        "exclude_patterns": json.dumps([]),
        "archive_name_template": "{plan_name}-{repo_name}-{now}",
        "compression": "lz4",
        "repository_run_mode": "series",
        "max_parallel_repositories": 1,
        "failure_behavior": "continue",
        "schedule_enabled": True,
        "cron_expression": "0 * * * *",
        "timezone": "UTC",
        "run_repository_scripts": False,
        "created_at": datetime.utcnow(),
    }
    values.update(overrides)
    plan = BackupPlan(**values)
    db.add(plan)
    db.flush()
    for index, repo in enumerate(repos):
        db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=index + 1,
                created_at=datetime.utcnow(),
            )
        )
    db.commit()
    return plan


def _run(db, plan, repos):
    run = BackupPlanRun(
        backup_plan_id=plan.id,
        trigger="schedule",
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    for repo in repos:
        db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id, repository_id=repo.id, status="pending"
            )
        )
    db.commit()
    return run


def _children(db, run):
    db.expire_all()
    return {
        child.repository_id: child
        for child in db.query(BackupPlanRunRepository).filter(
            BackupPlanRunRepository.backup_plan_run_id == run.id
        )
    }


# -- point 2 and 3: no run for an agent that is away -----------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plan_skips_the_repository_of_an_offline_agent(
    test_db, connected, failure_notifications
):
    laptop = _agent(test_db, "laptop", last_seen_ago=timedelta(minutes=50))
    repo = _repo(test_db, "laptop", laptop)
    plan = _plan(test_db, [repo])
    run = _run(test_db, plan, [repo])

    with patch(
        "app.services.operations.backup_facade.wait_for_backup_operation",
        new_callable=AsyncMock,
    ) as waited:
        await backup_plan_execution_service.execute_run(run.id)

    waited.assert_not_awaited()
    child = _children(test_db, run)[repo.id]
    assert child.status == "skipped"
    assert child.error_message == (
        "Skipped: agent offline; the backup was not started."
    )
    operation = test_db.get(Operation, child.backup_operation_id)
    assert operation.status == "skipped"
    assert operation.skip_reason == "agent_offline"
    assert operation.started_at is not None
    assert test_db.query(AgentJob).count() == 0
    test_db.refresh(run)
    # nothing was backed up: not a success an availability plan's minimum
    # interval would count
    assert run.status == "skipped"
    assert run.skip_reason == "agent_offline"
    failure_notifications.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["deleted", "revoked", "disabled"])
async def test_repository_of_a_gone_agent_is_not_skipped(
    test_db, connected, failure_notifications, status
):
    """An agent that was deleted, revoked or disabled has no session either,
    but it is not coming back: its backup takes the normal path, whose
    executor refuses it and reports the failure, instead of being skipped
    quietly on every run."""
    gone = _agent(test_db, "gone", last_seen_ago=timedelta(days=2))
    gone.status = status
    test_db.commit()
    repo = _repo(test_db, "gone", gone)
    plan = _plan(test_db, [repo])
    run = _run(test_db, plan, [repo])

    with patch(
        "app.services.operations.backup_facade.wait_for_backup_operation",
        new=AsyncMock(return_value="failed"),
    ) as waited:
        await backup_plan_execution_service.execute_run(run.id)

    waited.assert_awaited_once()
    assert _children(test_db, run)[repo.id].status == "failed"
    assert (
        test_db.query(Operation)
        .filter(Operation.skip_reason == "agent_offline")
        .count()
        == 0
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_failed_check_leaves_the_repository_to_the_normal_path(
    test_db, connected, monkeypatch
):
    """A database error while checking the agent does not fail the run: the
    repository gets its backup as it did before."""
    from sqlalchemy.exc import OperationalError

    import app.services.backup_plan_execution_service as plan_service

    laptop = _agent(test_db, "laptop", last_seen_ago=timedelta(minutes=50))
    repo = _repo(test_db, "laptop", laptop)
    plan = _plan(test_db, [repo])
    run = _run(test_db, plan, [repo])
    original = plan_service._write_bookkeeping

    def bookkeeping(work, **kwargs):
        if getattr(work, "__qualname__", "").startswith(
            "BackupPlanExecutionService._skip_if_agent_offline"
        ):
            raise OperationalError("SELECT 1", {}, Exception("disk I/O error"))
        return original(work, **kwargs)

    monkeypatch.setattr(plan_service, "_write_bookkeeping", bookkeeping)

    with patch(
        "app.services.operations.backup_facade.wait_for_backup_operation",
        new=AsyncMock(return_value="completed"),
    ) as waited:
        await backup_plan_execution_service.execute_run(run.id)

    waited.assert_awaited_once()
    test_db.refresh(run)
    assert run.status != "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recently_seen_agent_without_a_session_still_gets_its_backup(
    test_db, connected, failure_notifications
):
    """Right after a server start no agent has reconnected yet: an agent
    seen moments ago is not taken for away."""
    agent = _agent(test_db, "server", last_seen_ago=timedelta(seconds=30))
    repo = _repo(test_db, "server", agent)
    plan = _plan(test_db, [repo])
    run = _run(test_db, plan, [repo])

    with patch(
        "app.services.operations.backup_facade.wait_for_backup_operation",
        new=AsyncMock(return_value="completed"),
    ) as waited:
        await backup_plan_execution_service.execute_run(run.id)

    waited.assert_awaited_once()
    assert _children(test_db, run)[repo.id].status != "skipped"
    failure_notifications.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_every_missed_run_is_recorded_and_none_is_notified(
    test_db, connected, failure_notifications
):
    laptop = _agent(test_db, "laptop", last_seen_ago=timedelta(hours=3))
    repo = _repo(test_db, "laptop", laptop)
    plan = _plan(test_db, [repo])

    for _ in range(3):
        await backup_plan_execution_service.execute_run(_run(test_db, plan, [repo]).id)

    assert (
        test_db.query(Operation)
        .filter(Operation.skip_reason == "agent_offline")
        .count()
        == 3
    )
    failure_notifications.assert_not_awaited()


# -- point 4: a queued backup whose agent went away ------------------------


def _queued_backup(db, repo, *, plan_run=None, age):
    from app.services.operations.enqueue import enqueue

    operation = enqueue(
        db,
        "backup",
        repository_id=repo.id,
        trigger="plan" if plan_run is not None else "manual",
        backup_plan_run_id=plan_run.id if plan_run is not None else None,
        params={"executor": "agent"},
    )
    operation.status = "running"
    created = _ago(age)
    job = AgentJob(
        agent_machine_id=repo.agent_machine_id,
        operation_id=operation.id,
        job_type="backup",
        status="queued",
        payload={"job_kind": "backup.create"},
        created_at=created,
        updated_at=created,
    )
    db.add(job)
    db.commit()
    return operation, job


# 12:00:30 UTC: a backup its plan queued at noon
_QUEUED_AT = datetime(2026, 10, 20, 12, 0, 30, tzinfo=timezone.utc)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cron", "schedule_enabled", "waited", "skipped"),
    [
        # hourly: the 13:00 run covers the same data
        ("0 * * * *", True, timedelta(minutes=50), False),
        ("0 * * * *", True, timedelta(minutes=70), True),
        # daily: no more than four hours
        ("0 2 * * *", True, timedelta(hours=3, minutes=50), False),
        ("0 2 * * *", True, timedelta(hours=4, minutes=10), True),
        # uneven: the next run after the backup's own, not the gap after it
        ("0 0,12,13 * * *", True, timedelta(minutes=70), True),
        # a plan whose schedule is off has no next run: four hours
        ("0 * * * *", False, timedelta(minutes=70), False),
        ("0 * * * *", False, timedelta(hours=4, minutes=10), True),
    ],
)
def test_queued_backup_waits_until_its_plans_next_run_at_most_four_hours(
    db_session, cron, schedule_enabled, waited, skipped
):
    from app.services.agent_job_reaper import skip_backup_jobs_of_offline_agents

    laptop = _agent(db_session, "laptop", last_seen_ago=timedelta(days=1))
    laptop.last_seen_at = _naive(_QUEUED_AT - timedelta(minutes=1))
    repo = _repo(db_session, "laptop", laptop)
    plan = _plan(
        db_session, [repo], cron_expression=cron, schedule_enabled=schedule_enabled
    )
    operation, job = _queued_backup(
        db_session, repo, plan_run=_run(db_session, plan, [repo]), age=timedelta(0)
    )
    job.created_at = _naive(_QUEUED_AT)
    db_session.commit()

    assert skip_backup_jobs_of_offline_agents(db_session, now=_QUEUED_AT + waited) == (
        1 if skipped else 0
    )

    db_session.refresh(job)
    db_session.refresh(operation)
    if skipped:
        assert job.status == "canceled"
        assert operation.status == "skipped"
        assert operation.skip_reason == "agent_offline"
        assert operation.error_message.startswith("Skipped: agent offline")
    else:
        assert job.status == "queued"
        assert operation.status == "running"


@pytest.mark.unit
def test_wait_counts_from_the_later_of_job_and_agent(db_session):
    """A manual backup queued for an agent gone for a day still gets the
    four hours; one whose agent left an hour ago, queued five hours ago,
    gets them from the agent's last report."""
    from app.services.agent_job_reaper import skip_backup_jobs_of_offline_agents

    gone = _agent(db_session, "gone", last_seen_ago=timedelta(days=1))
    _, fresh = _queued_backup(
        db_session, _repo(db_session, "gone", gone), age=timedelta(hours=1)
    )
    left = _agent(db_session, "left", last_seen_ago=timedelta(hours=1))
    _, old = _queued_backup(
        db_session, _repo(db_session, "left", left), age=timedelta(hours=5)
    )

    assert skip_backup_jobs_of_offline_agents(db_session) == 0
    db_session.refresh(fresh)
    db_session.refresh(old)
    assert (fresh.status, old.status) == ("queued", "queued")


@pytest.mark.unit
def test_day_long_pass_leaves_backup_jobs_to_their_own_deadline(db_session):
    """Backups end skipped, never failed by the 24 h pass for other jobs."""
    from app.services.agent_job_reaper import reap_queued_jobs_of_offline_agents

    gone = _agent(db_session, "gone", last_seen_ago=timedelta(hours=25))
    operation, job = _queued_backup(
        db_session, _repo(db_session, "gone", gone), age=timedelta(minutes=5)
    )

    assert reap_queued_jobs_of_offline_agents(db_session) == 0
    db_session.refresh(job)
    assert job.status == "queued"


@pytest.mark.unit
@pytest.mark.parametrize("status", ["revoked", "disabled"])
def test_backup_of_a_gone_agent_still_fails_and_is_reported(db_session, status):
    """Revoking an agent leaves its queued jobs: such a backup is not skipped
    as if the agent were only away, the day-long pass fails it and reports
    it, as before."""
    from app.services.agent_job_reaper import (
        reap_queued_jobs_of_offline_agents,
        skip_backup_jobs_of_offline_agents,
    )

    gone = _agent(db_session, "gone", last_seen_ago=timedelta(hours=25))
    gone.status = status
    db_session.commit()
    operation, job = _queued_backup(
        db_session, _repo(db_session, "gone", gone), age=timedelta(hours=5)
    )

    assert skip_backup_jobs_of_offline_agents(db_session) == 0
    failed: list[int] = []
    assert (
        reap_queued_jobs_of_offline_agents(db_session, failed_backup_job_ids=failed)
        == 1
    )

    db_session.refresh(job)
    db_session.refresh(operation)
    assert job.status == "failed"
    assert operation.status == "failed"
    assert operation.skip_reason is None
    assert failed == [operation.id]


@pytest.mark.unit
def test_returning_agent_keeps_its_backup(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    import app.services.agent_job_reaper as agent_job_reaper

    laptop = _agent(db_session, "laptop", last_seen_ago=timedelta(hours=5))
    _, job = _queued_backup(
        db_session, _repo(db_session, "laptop", laptop), age=timedelta(hours=5)
    )
    agent_id = laptop.id
    original = agent_job_reaper._fail_agent_job

    def reconnect_then_skip(db, *args, **kwargs):
        other = sessionmaker(bind=db_session.get_bind())()
        try:
            other.query(AgentMachine).filter(AgentMachine.id == agent_id).update(
                {"last_seen_at": _ago(timedelta(0)), "status": "online"},
                synchronize_session=False,
            )
            other.commit()
        finally:
            other.close()
        return original(db, *args, **kwargs)

    monkeypatch.setattr(agent_job_reaper, "_fail_agent_job", reconnect_then_skip)

    assert agent_job_reaper.skip_backup_jobs_of_offline_agents(db_session) == 0
    db_session.refresh(job)
    assert job.status == "queued"


# -- the executor around a skipped backup ----------------------------------


class _Ctx:
    def __init__(self, db, operation):
        self.db = db
        self.operation_id = operation.id
        self.repository_id = operation.repository_id
        self.params = dict(operation.params or {})

    def cancelled(self):
        return False


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("pre_ran", [True, False])
async def test_post_hooks_after_a_skip_run_only_once_a_pre_hook_ran(
    db_session, monkeypatch, pre_ran
):
    """A pre-backup hook that stopped a service has its post-backup hook
    start it again, also when the agent went away before it got the backup;
    without one there is nothing to undo, and no hook is sent to an agent
    that is away."""
    import app.services.operations.executors.backup as backup_executor
    from app.services.agent_repository_hooks import AgentHookResult
    from app.services.operations.backup_facade import BackupJobFacade

    laptop = _agent(db_session, "laptop", last_seen_ago=timedelta(hours=5))
    repo = _repo(db_session, "laptop", laptop)
    operation, _ = _queued_backup(db_session, repo, age=timedelta(hours=5))
    hook_calls: list[tuple[str, object]] = []

    async def hooks(db, repository, *, operation_id, hook_type, **kwargs):
        hook_calls.append((hook_type, kwargs.get("backup_result")))
        return AgentHookResult(executed=1 if pre_ran else 0)

    async def skipped_by_the_reaper(ctx, job, repository, params):
        op = ctx.db.get(Operation, ctx.operation_id)
        op.status = "skipped"
        op.skip_reason = "agent_offline"
        ctx.db.commit()

    monkeypatch.setattr(backup_executor, "run_agent_repository_hooks", hooks)
    monkeypatch.setattr(
        backup_executor, "_queue_and_wait_agent_backup", skipped_by_the_reaper
    )
    monkeypatch.setattr(backup_executor, "get_agent_job_for_backup", lambda *a: None)
    monkeypatch.setattr(
        backup_executor, "ensure_repository_admission", lambda *a, **k: None
    )
    monkeypatch.setattr(backup_executor, "agent_hooks", lambda *a: [object()])

    ctx = _Ctx(db_session, operation)
    await backup_executor._run_agent_backup(
        ctx, BackupJobFacade(db_session, operation), repo, ctx.params
    )

    assert hook_calls[0] == ("pre-backup", None)
    assert hook_calls[1:] == ([("post-backup", "skipped")] if pre_ran else [])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resumed_backup_skipped_later_still_runs_its_cleanup(
    db_session, monkeypatch
):
    """A backup resumed after a restart runs no pre-backup hook again; the
    one that ran before the restart still gets its post-backup hook."""
    import app.services.operations.executors.backup as backup_executor
    from app.database.models import ScriptExecution
    from app.services.agent_repository_hooks import AgentHookResult
    from app.services.operations.backup_facade import BackupJobFacade

    laptop = _agent(db_session, "laptop", last_seen_ago=timedelta(hours=5))
    repo = _repo(db_session, "laptop", laptop)
    operation, live_job = _queued_backup(db_session, repo, age=timedelta(hours=5))
    db_session.add(
        ScriptExecution(
            operation_id=operation.id,
            repository_id=repo.id,
            hook_type="pre-backup",
            status="completed",
        )
    )
    db_session.commit()
    hook_calls: list[tuple[str, object]] = []

    async def hooks(db, repository, *, operation_id, hook_type, **kwargs):
        hook_calls.append((hook_type, kwargs.get("backup_result")))
        return AgentHookResult(executed=1)

    async def skipped_by_the_reaper(ctx, job, repository, params):
        op = ctx.db.get(Operation, ctx.operation_id)
        op.status = "skipped"
        op.skip_reason = "agent_offline"
        ctx.db.commit()

    monkeypatch.setattr(backup_executor, "run_agent_repository_hooks", hooks)
    monkeypatch.setattr(
        backup_executor, "_queue_and_wait_agent_backup", skipped_by_the_reaper
    )
    monkeypatch.setattr(
        backup_executor, "get_agent_job_for_backup", lambda *a: live_job
    )
    monkeypatch.setattr(backup_executor, "agent_hooks", lambda *a: [object()])

    ctx = _Ctx(db_session, operation)
    await backup_executor._run_agent_backup(
        ctx, BackupJobFacade(db_session, operation), repo, ctx.params
    )

    assert hook_calls == [("post-backup", "skipped")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_cleanup_after_a_skip_fails_the_backup(db_session, monkeypatch):
    """A skip whose post-backup hook failed is not a graceful one: what the
    pre-backup hook stopped may still be stopped, and the user hears so."""
    import app.services.operations.executors.backup as backup_executor
    from app.services.agent_repository_hooks import AgentHookResult
    from app.services.operations.backup_facade import BackupJobFacade

    laptop = _agent(db_session, "laptop", last_seen_ago=timedelta(hours=5))
    repo = _repo(db_session, "laptop", laptop)
    operation, _ = _queued_backup(db_session, repo, age=timedelta(hours=5))

    async def hooks(db, repository, *, operation_id, hook_type, **kwargs):
        if hook_type == "pre-backup":
            return AgentHookResult(executed=1)
        return AgentHookResult(executed=1, failed=1, failures=["timed out"])

    async def skipped_by_the_reaper(ctx, job, repository, params):
        op = ctx.db.get(Operation, ctx.operation_id)
        op.status = "skipped"
        op.skip_reason = "agent_offline"
        op.error_message = "Skipped: agent offline"
        ctx.db.commit()

    notified = AsyncMock()
    monkeypatch.setattr(backup_executor, "run_agent_repository_hooks", hooks)
    monkeypatch.setattr(
        backup_executor, "_queue_and_wait_agent_backup", skipped_by_the_reaper
    )
    monkeypatch.setattr(backup_executor, "get_agent_job_for_backup", lambda *a: None)
    monkeypatch.setattr(
        backup_executor, "ensure_repository_admission", lambda *a, **k: None
    )
    monkeypatch.setattr(backup_executor, "agent_hooks", lambda *a: [object()])
    monkeypatch.setattr(backup_executor, "notify_backup_job_finished", notified)

    ctx = _Ctx(db_session, operation)
    await backup_executor._run_agent_backup(
        ctx, BackupJobFacade(db_session, operation), repo, ctx.params
    )

    db_session.expire_all()
    op = db_session.get(Operation, operation.id)
    assert op.status == "failed"
    assert op.error_message.startswith("Skipped: agent offline\n")
    assert "postBackupHooksAlsoFailed" in op.error_message
    notified.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_whose_backups_the_reaper_skipped_is_skipped(test_db, connected):
    """The agent was there when the run started and went away before it got
    the backup: the run backed nothing up either, and keeps the plan's
    post-backup warning."""
    agent = _agent(test_db, "laptop", last_seen_ago=timedelta(seconds=10))
    connected.add(agent.id)
    repo = _repo(test_db, "laptop", agent)
    plan = _plan(test_db, [repo])
    run = _run(test_db, plan, [repo])

    async def skipped_by_the_reaper(db, operation_id, **_ignored):
        operation = db.get(Operation, operation_id)
        operation.status = "skipped"
        operation.skip_reason = "agent_offline"
        operation.error_message = "Skipped: agent offline for over 60 minutes"
        operation.completed_at = datetime.utcnow()
        db.commit()
        return "skipped"

    with (
        patch(
            "app.services.operations.backup_facade.wait_for_backup_operation",
            new=skipped_by_the_reaper,
        ),
        patch.object(
            backup_plan_execution_service,
            "_execute_plan_script_hooks",
            new=AsyncMock(
                side_effect=[(True, None, False), (False, "cleanup failed", False)]
            ),
        ),
    ):
        await backup_plan_execution_service.execute_run(run.id)

    test_db.refresh(run)
    assert run.status == "skipped"
    assert run.skip_reason == "agent_offline"
    assert "cleanup failed" in run.error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_waiting_for_the_agent_holds_no_connection_while_asleep(
    db_session, monkeypatch
):
    """Backups for agents that are away hold no slot, so any number of them
    wait at once: none may keep a pooled connection while it sleeps."""
    import app.services.repository_executor as repository_executor

    laptop = _agent(db_session, "laptop", last_seen_ago=timedelta(hours=1))
    operation, job = _queued_backup(
        db_session, _repo(db_session, "laptop", laptop), age=timedelta(minutes=5)
    )
    in_transaction: list[bool] = []

    async def sleep(_seconds):
        in_transaction.append(db_session.in_transaction())
        job.status = "canceled"
        db_session.commit()

    monkeypatch.setattr(repository_executor.asyncio, "sleep", sleep)

    await repository_executor.wait_for_agent_backup_job(
        db_session, job.id, operation.id, lambda: False
    )

    assert in_transaction == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_waiting_for_a_hook_holds_no_connection_while_asleep(
    db_session, monkeypatch
):
    """The repository hooks of such a backup are agent jobs as well, waited
    for before the backup's own job exists."""
    import app.services.repository_executor as repository_executor

    laptop = _agent(db_session, "laptop", last_seen_ago=timedelta(hours=1))
    job = AgentJob(
        agent_machine_id=laptop.id,
        job_type="script",
        status="queued",
        payload={"job_kind": "script.run"},
    )
    db_session.add(job)
    db_session.commit()
    in_transaction: list[bool] = []

    async def sleep(_seconds):
        in_transaction.append(db_session.in_transaction())
        job.status = "completed"
        db_session.commit()

    monkeypatch.setattr(repository_executor.asyncio, "sleep", sleep)

    await repository_executor.wait_for_agent_script_job(db_session, job.id)

    assert in_transaction == [False]
