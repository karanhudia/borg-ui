"""A backup an agent runs goes on through a server restart.

The server has no Borg process to stop: a shutdown leaves the operation
`running` and its agent job as it is, and the next process's recovery waits
on that job again, so what the agent reports is recorded the way it would
have been without the restart.
"""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.database.database as database
import app.services.operations.runner as runner_module
from app.api.agents import (
    AgentJobCompleteRequest,
    AgentJobFailRequest,
    _cancel_agent_job,
    _record_job_completion,
    _record_job_failure,
)
from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentMachine,
    Base,
    Operation,
    Repository,
    SystemSettings,
)
from app.services.operations.backup_facade import BackupJobFacade
from app.services.operations.enqueue import enqueue
from app.services.operations.executors import backup as backup_executor
from app.services.operations.runner import OperationRunner

COMPLETED = AgentJobCompleteRequest(
    result={"return_code": 0, "archive_name": "the-archive"}
)


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'restart.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.execute("PRAGMA busy_timeout=5000")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return factory


@pytest.fixture()
def chains(monkeypatch):
    """The operations whose follow-up chain the runner's terminal write
    enqueued."""
    enqueued: list[int] = []
    monkeypatch.setattr(
        runner_module,
        "enqueue_followups",
        lambda db, operation, **kwargs: enqueued.append(operation.id) or [],
    )
    return enqueued


def _process(monkeypatch) -> OperationRunner:
    """A server process's runner: the one the agent transport asks whether a
    task is waiting on the job it reports."""
    runner = OperationRunner(poll_interval=0.01)
    monkeypatch.setattr(runner_module, "operation_runner", runner)
    return runner


def _seed(db, **params):
    agent = AgentMachine(
        name="a",
        agent_id="agt_a",
        token_hash=get_password_hash("secret"),
        token_prefix="secret-a",
        status="online",
        capabilities=["backup.create", "jobs.cancel"],
        agent_version="0.1.25",
        created_at=datetime.utcnow(),
    )
    db.add(agent)
    db.add(SystemSettings())
    db.commit()
    repo = Repository(
        name="r",
        path="/repos/r",
        encryption="none",
        compression="lz4",
        repository_type="local",
        mode="full",
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=agent.id,
    )
    db.add(repo)
    db.commit()
    op = enqueue(
        db,
        "backup",
        repository_id=repo.id,
        trigger="manual",
        params={
            "executor": "agent",
            "source_directories": ["/home"],
            "archive_name": "the-archive",
            "skip_hooks": True,
            **params,
        },
    )
    db.commit()
    return agent.id, op.id


async def _start_agent_backup(factory, runner) -> int:
    """Dispatch the backup and let the agent claim and start its job."""
    assert runner.acquire_lease(factory())
    assert await runner.tick() == 1
    db = factory()
    try:
        job = None
        for _ in range(100):
            db.expire_all()
            job = db.query(AgentJob).first()
            if job is not None:
                break
            await asyncio.sleep(0.05)
        assert job is not None, "the executor queued no agent job"
        job.status = "running"
        job.claimed_at = job.started_at = datetime.utcnow()
        db.commit()
        return job.id
    finally:
        db.close()


def _state(factory, op_id, job_id):
    db = factory()
    try:
        op = db.get(Operation, op_id)
        job = db.get(AgentJob, job_id)
        return op.status, job.status
    finally:
        db.close()


async def _shut_down(runner) -> None:
    runner.stop()
    await asyncio.wait_for(runner.drain(timeout=20.0), timeout=5.0)


async def _restart(factory, monkeypatch) -> OperationRunner:
    """The next process: lease, recovery, and the tasks recovery asks for."""
    replacement = _process(monkeypatch)
    assert replacement.acquire_lease(factory())
    db = factory()
    try:
        replacement.recover_on_startup(db)
    finally:
        db.close()
    replacement.attach_recovered()
    return replacement


async def _ended(runner, op_id) -> None:
    task = runner.running_tasks.get(op_id)
    assert task is not None, "no task waits on the operation"
    await asyncio.wait_for(task, timeout=10.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shutdown_leaves_a_running_agent_backup_to_its_agent(
    session_factory, monkeypatch, chains
):
    agent_id, op_id = _seed(session_factory())
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)

    await _shut_down(runner)

    # no cancel is owed to the agent, and the record is not ended
    assert _state(session_factory, op_id, job_id) == ("running", "running")
    assert not runner.running_tasks
    assert not runner.cancel_requested
    assert not runner.unrecorded_outcomes
    assert chains == []
    # the drain did not wait on the agent, so the lease is handed over
    assert not runner._drain_timed_out
    assert OperationRunner(poll_interval=0.01).acquire_lease(session_factory())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_next_process_waits_on_the_agent_job_again(
    session_factory, monkeypatch, chains
):
    agent_id, op_id = _seed(session_factory())
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    await _shut_down(runner)

    replacement = await _restart(session_factory, monkeypatch)
    assert list(replacement.running_tasks) == [op_id]
    await asyncio.sleep(0.2)
    # still the agent's backup, and still one job for it
    assert _state(session_factory, op_id, job_id) == ("running", "running")
    assert session_factory().query(AgentJob).count() == 1

    _record_job_completion(job_id, COMPLETED, agent_id)
    await _ended(replacement, op_id)

    assert _state(session_factory, op_id, job_id) == ("completed", "completed")
    db = session_factory()
    op = db.get(Operation, op_id)
    # the runner's terminal write, not the transport's alone
    assert op.result is not None
    assert BackupJobFacade(db, op).archive_name == "the-archive"
    assert chains == [op_id]
    assert db.query(AgentJob).count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_killed_process_is_followed_the_same_way(
    session_factory, monkeypatch, chains
):
    agent_id, op_id = _seed(session_factory())
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    # killed: no drain, and its lease has run out
    for task in list(runner.running_tasks.values()):
        task.cancel()
    runner._detached.add(op_id)
    await asyncio.gather(*runner.running_tasks.values(), return_exceptions=True)
    db = session_factory()
    runner.release_lease(db)
    db.close()
    assert _state(session_factory, op_id, job_id) == ("running", "running")

    replacement = await _restart(session_factory, monkeypatch)
    _record_job_completion(job_id, COMPLETED, agent_id)
    await _ended(replacement, op_id)

    assert _state(session_factory, op_id, job_id) == ("completed", "completed")
    assert chains == [op_id]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_report_during_the_downtime_is_recorded_after_it(
    session_factory, monkeypatch, chains
):
    """The agent finished while no server ran and redelivers its outcome to
    the next one, whose recovery ran before it served the report."""
    agent_id, op_id = _seed(session_factory())
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    await _shut_down(runner)

    replacement = await _restart(session_factory, monkeypatch)
    _record_job_completion(job_id, COMPLETED, agent_id)
    await _ended(replacement, op_id)

    db = session_factory()
    op = db.get(Operation, op_id)
    assert (op.status, op.error_message) == ("completed", None)
    assert chains == [op_id]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancel_after_the_restart_still_reaches_the_agent(
    session_factory, monkeypatch, chains
):
    agent_id, op_id = _seed(session_factory())
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    await _shut_down(runner)
    replacement = await _restart(session_factory, monkeypatch)

    assert await replacement.request_cancel(op_id) is True
    for _ in range(100):
        if _state(session_factory, op_id, job_id)[1] == "cancel_requested":
            break
        await asyncio.sleep(0.05)
    assert _state(session_factory, op_id, job_id) == ("running", "cancel_requested")

    db = session_factory()
    _cancel_agent_job(db.get(AgentJob, job_id), db)
    db.commit()
    db.close()
    await _ended(replacement, op_id)

    assert _state(session_factory, op_id, job_id) == ("cancelled", "canceled")
    assert chains == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_running_backup_without_a_live_agent_job_fails_as_before(
    session_factory, monkeypatch, chains
):
    agent_id, op_id = _seed(session_factory())
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    await _shut_down(runner)
    # the agent job ended without its backup's row following
    db = session_factory()
    db.get(AgentJob, job_id).status = "failed"
    db.commit()
    db.close()

    replacement = await _restart(session_factory, monkeypatch)

    assert not replacement.running_tasks
    db = session_factory()
    op = db.get(Operation, op_id)
    assert (op.status, op.error_message) == ("failed", "interrupted by restart")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_plan_backup_waited_on_again_does_not_enter_its_slot_twice(
    session_factory, monkeypatch, chains
):
    """The plan's pre-backup scripts ran before the restart; the run they
    belong to has ended since, and asking for its slot again would stand the
    backup down while the agent runs it."""
    from app.database.models import BackupPlan, BackupPlanRun

    db = session_factory()
    agent_id, op_id = _seed(db)
    plan = BackupPlan(name="p", source_directories="[]")
    db.add(plan)
    db.commit()
    run = BackupPlanRun(backup_plan_id=plan.id, status="running", trigger="manual")
    db.add(run)
    db.commit()
    db.get(Operation, op_id).backup_plan_run_id = run.id
    db.commit()
    entered: list[int] = []

    async def enter(ctx):
        entered.append(ctx.operation_id)
        return None

    monkeypatch.setattr(backup_executor, "_enter_plan_slot", enter)
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    assert entered == [op_id]
    await _shut_down(runner)

    replacement = await _restart(session_factory, monkeypatch)
    _record_job_completion(job_id, COMPLETED, agent_id)
    await _ended(replacement, op_id)

    assert entered == [op_id]
    assert _state(session_factory, op_id, job_id) == ("completed", "completed")


def _hooks_on_record(
    db,
    op_id,
    *,
    pre_hook=True,
    post_hook=True,
    pre_status="completed",
    message=None,
    run_on=None,
):
    """The repository as a backup with agent hooks leaves it once its
    pre-backup hook ran: the hook's execution on record, and a post-backup
    hook configured that starts again what the first one stopped."""
    from app.database.models import RepositoryScript, ScriptExecution

    operation = db.get(Operation, op_id)
    if post_hook:
        db.add(
            RepositoryScript(
                repository_id=operation.repository_id,
                agent_script_name="start-db",
                hook_type="post-backup",
                execution_order=1,
                enabled=True,
                custom_run_on=run_on,
            )
        )
    if pre_hook:
        db.add(
            ScriptExecution(
                agent_script_name="stop-db",
                repository_id=operation.repository_id,
                operation_id=op_id,
                hook_type="pre-backup",
                status=pre_status,
                error_message=message,
                started_at=datetime.utcnow(),
                triggered_by="backup",
            )
        )
    db.commit()


def _post_hooks(monkeypatch, session_factory):
    """Stands in for the agent running the post-backup hooks: records what
    they were told and leaves the execution a hook leaves."""
    from app.database.models import ScriptExecution
    from app.services.agent_repository_hooks import AgentHookResult

    heard = []

    async def run(db, repository, *, operation_id, hook_type, backup_result=None, **_):
        heard.append((hook_type, backup_result))
        aside = session_factory()
        aside.add(
            ScriptExecution(
                agent_script_name="start-db",
                repository_id=repository.id,
                operation_id=operation_id,
                hook_type=hook_type,
                status="completed",
                started_at=datetime.utcnow(),
                triggered_by="backup",
            )
        )
        aside.commit()
        aside.close()
        return AgentHookResult(executed=1)

    monkeypatch.setattr(backup_executor, "run_agent_repository_hooks", run)
    return heard


@pytest.mark.unit
@pytest.mark.asyncio
async def test_post_hooks_a_report_before_recovery_left_owed_run_after_it(
    session_factory, monkeypatch, chains
):
    """The agent's report reached a process that had not recovered yet and
    closed the row with no task behind it. What the pre-backup hook stopped
    is still stopped: recovery has the post-backup hooks run, once."""
    agent_id, op_id = _seed(session_factory(), skip_hooks=False)
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    _hooks_on_record(session_factory(), op_id)
    await _shut_down(runner)
    heard = _post_hooks(monkeypatch, session_factory)

    _process(monkeypatch)  # serving, not recovered yet
    _record_job_completion(job_id, COMPLETED, agent_id)
    assert _state(session_factory, op_id, job_id) == ("completed", "completed")
    assert heard == []

    replacement = await _restart(session_factory, monkeypatch)
    await _ended(replacement, op_id)

    assert heard == [("post-backup", "success")]
    db = session_factory()
    op = db.get(Operation, op_id)
    assert (op.status, op.result is not None) == ("completed", True)

    # they ran: the next restart owes the backup nothing
    replacement.release_lease(db)
    db.close()
    again = await _restart(session_factory, monkeypatch)
    assert not again.running_tasks
    assert heard == [("post-backup", "success")]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("pre_status", ["warning", "failed"])
async def test_a_resumed_backup_keeps_what_its_pre_hooks_left_to_say(
    session_factory, monkeypatch, chains, pre_status
):
    """The pre-backup hooks are not run again; a warning of one, or a
    failure the backup was allowed to go on after, still makes the backup
    end with a warning, and its post-backup hooks hear so."""
    agent_id, op_id = _seed(session_factory(), skip_hooks=False)
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    _hooks_on_record(
        session_factory(), op_id, pre_status=pre_status, message="stop-db said so"
    )
    await _shut_down(runner)
    heard = _post_hooks(monkeypatch, session_factory)

    replacement = await _restart(session_factory, monkeypatch)
    _record_job_completion(job_id, COMPLETED, agent_id)
    await _ended(replacement, op_id)

    assert heard == [("post-backup", "warning")]
    db = session_factory()
    op = db.get(Operation, op_id)
    assert op.status == "completed_with_warnings"
    assert "stop-db said so" in (op.error_message or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_owed_post_hooks_hear_the_warning_a_pre_hook_left(
    session_factory, monkeypatch, chains
):
    """A post-backup hook that runs on a warning only is owed after a
    backup whose pre-backup hook warned, although the agent reported
    success: that is what the backup's own task would have told it."""
    agent_id, op_id = _seed(session_factory(), skip_hooks=False)
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    _hooks_on_record(
        session_factory(),
        op_id,
        pre_status="warning",
        message="stop-db said so",
        run_on="warning",
    )
    await _shut_down(runner)
    heard = _post_hooks(monkeypatch, session_factory)

    _process(monkeypatch)  # serving, not recovered yet
    _record_job_completion(job_id, COMPLETED, agent_id)
    replacement = await _restart(session_factory, monkeypatch)
    await _ended(replacement, op_id)

    assert heard == [("post-backup", "warning")]
    db = session_factory()
    assert db.get(Operation, op_id).status == "completed_with_warnings"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_report_before_recovery_ends_the_row_and_recovery_finishes_it(
    session_factory, monkeypatch, chains
):
    """A replacement that serves requests while the old process still holds
    the lease records the agent's report before its own recovery: the row
    ends with the agent's verdict, and without what the runner writes last.
    Recovery has a task finish it, once."""
    agent_id, op_id = _seed(session_factory())
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    await _shut_down(runner)

    _process(monkeypatch)  # serving, not recovered yet
    _record_job_completion(job_id, COMPLETED, agent_id)
    assert _state(session_factory, op_id, job_id) == ("completed", "completed")
    db = session_factory()
    assert db.get(Operation, op_id).result is None
    db.close()

    replacement = await _restart(session_factory, monkeypatch)
    await _ended(replacement, op_id)

    db = session_factory()
    op = db.get(Operation, op_id)
    assert (op.status, op.result is not None) == ("completed", True)
    assert chains == [op_id]
    assert db.query(AgentJob).count() == 1

    replacement.release_lease(db)
    db.close()
    again = await _restart(session_factory, monkeypatch)
    assert not again.running_tasks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_post_hooks_are_owed_without_a_pre_hook_too(
    session_factory, monkeypatch, chains
):
    """A repository with post-backup hooks only: its backup's own task
    would have run them."""
    agent_id, op_id = _seed(session_factory(), skip_hooks=False)
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    _hooks_on_record(session_factory(), op_id, pre_hook=False)
    await _shut_down(runner)
    heard = _post_hooks(monkeypatch, session_factory)

    _process(monkeypatch)  # serving, not recovered yet
    _record_job_completion(job_id, COMPLETED, agent_id)
    replacement = await _restart(session_factory, monkeypatch)
    await _ended(replacement, op_id)

    assert heard == [("post-backup", "success")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_pre_hook_warning_counts_without_a_post_hook_too(
    session_factory, monkeypatch, chains
):
    """No post-backup hook is due, and the backup still ends with the
    warning its pre-backup hook left, as it does when its own task ends it."""
    agent_id, op_id = _seed(session_factory(), skip_hooks=False)
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    _hooks_on_record(
        session_factory(),
        op_id,
        post_hook=False,
        pre_status="warning",
        message="stop-db said so",
    )
    await _shut_down(runner)
    heard = _post_hooks(monkeypatch, session_factory)

    _process(monkeypatch)  # serving, not recovered yet
    _record_job_completion(job_id, COMPLETED, agent_id)
    assert _state(session_factory, op_id, job_id) == ("completed", "completed")
    replacement = await _restart(session_factory, monkeypatch)
    await _ended(replacement, op_id)

    assert heard == []
    db = session_factory()
    op = db.get(Operation, op_id)
    assert op.status == "completed_with_warnings"
    assert "stop-db said so" in (op.error_message or "")


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("pre_hook", [True, False])
async def test_a_failed_backup_is_owed_its_cleanup_only(
    session_factory, monkeypatch, chains, pre_hook
):
    """A backup that failed has no result to tell an unfinished one by:
    recovery takes it up only for the post-backup hooks that undo what a
    pre-backup hook did."""
    agent_id, op_id = _seed(session_factory(), skip_hooks=False)
    runner = _process(monkeypatch)
    job_id = await _start_agent_backup(session_factory, runner)
    _hooks_on_record(session_factory(), op_id, pre_hook=pre_hook)
    await _shut_down(runner)
    heard = _post_hooks(monkeypatch, session_factory)

    _process(monkeypatch)  # serving, not recovered yet
    _record_job_failure(
        job_id,
        AgentJobFailRequest(error_message="borg exited with code 2", return_code=2),
        agent_id,
    )
    assert _state(session_factory, op_id, job_id) == ("failed", "failed")
    replacement = await _restart(session_factory, monkeypatch)

    if not pre_hook:
        assert not replacement.running_tasks
        assert heard == []
        return
    await _ended(replacement, op_id)
    assert heard == [("post-backup", "failure")]
    assert _state(session_factory, op_id, job_id) == ("failed", "failed")
