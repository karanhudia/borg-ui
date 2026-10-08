"""#1386: an agent repository's own pre/post-backup hooks.

They are scripts the agent publishes, run as `script.run` jobs around the
agent backup; inline shell scripts and server library scripts cannot run
for an agent repository and are reported instead of passed over.
"""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    AgentJob,
    AgentMachine,
    Base,
    Operation,
    Repository,
    RepositoryScript,
    Script,
    ScriptExecution,
)
from app.services.operations.backup_facade import BackupJobFacade
from app.services.operations.executors import get_executor, load_default_executors
from app.services.script_library_executor import ScriptLibraryExecutor

from tests.unit.test_operations_backup_executor import FakeContext, _operation

HOOKS = "app.services.agent_repository_hooks"
EXECUTOR = "app.services.operations.executors.backup"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repository(db):
    repo = Repository(
        name="nas", path="/repo/nas", borg_version=1, repository_type="local"
    )
    db.add(repo)
    db.commit()
    return repo


@pytest.fixture()
def agent_repo(db, repository):
    agent = AgentMachine(
        name="host", agent_id="agt_host", token_hash="x", token_prefix="x"
    )
    db.add(agent)
    db.flush()
    repository.executor_type = "agent"
    repository.execution_target = "agent"
    repository.agent_machine_id = agent.id
    db.commit()
    return repository


def _hook(db, repository, name, hook_type, **kw):
    row = RepositoryScript(
        repository_id=repository.id,
        agent_script_name=name,
        hook_type=hook_type,
        execution_order=kw.pop("order", 1),
        **kw,
    )
    db.add(row)
    db.commit()
    return row


class Agent:
    """Stands in for the agent: records the jobs it is sent and answers
    them; `rc` maps a script name to its return code."""

    def __init__(self, db, monkeypatch, *, rc=None, backup="completed"):
        self.db = db
        self.rc = rc or {}
        self.backup_status = backup
        self.calls = []
        self.queue_error = None
        self.envs = {}
        self._jobs = {}

        def _queue_script(session, agent, *, script_name, env):
            agent_job = AgentJob(
                agent_machine_id=agent.id,
                job_type="script",
                status="queued",
                payload={},
            )
            session.add(agent_job)
            session.commit()
            self._jobs[agent_job.id] = script_name
            self.envs[script_name] = env
            return agent_job

        async def _dispatch(session, agent_job, **context):
            return True

        self.status_under = {}
        self.raise_on = set()

        async def _wait_script(session, agent_job_id, *, is_cancelled, timeout_seconds):
            name = self._jobs[agent_job_id]
            self.calls.append(name)
            if name in self.raise_on:
                raise RuntimeError(f"{name} broke")
            session.expire_all()
            ops = session.query(Operation).all()
            self.status_under[name] = ops[-1].status if ops else None
            return {
                "status": "completed",
                "result": {
                    "return_code": self.rc.get(name, 0),
                    "stdout": f"{name} out",
                    "stderr": "",
                },
            }

        def _queue_backup(session, backup_job, repo, **kw):
            if self.queue_error is not None:
                raise self.queue_error
            self.calls.append("backup")
            backup_job.execution_mode = "agent"
            return SimpleNamespace(id=77, payload={})

        async def _wait_backup(
            session, agent_job_id, backup_job_id, is_cancelled, **kw
        ):
            job = BackupJobFacade(db, db.get(Operation, backup_job_id))
            job.status = self.backup_status
            if self.backup_status != "running":
                # the agent transport ends the row when the agent reports
                job.completed_at = datetime(2026, 10, 8, 2)
            db.commit()
            return self.backup_status

        self.notified = []

        async def _notify(session, job):
            self.notified.append(job.status)

        monkeypatch.setattr(f"{HOOKS}.queue_agent_script_job", _queue_script)
        monkeypatch.setattr(f"{HOOKS}.dispatch_agent_job_best_effort", _dispatch)
        monkeypatch.setattr(f"{HOOKS}.wait_for_agent_script_job", _wait_script)
        monkeypatch.setattr(f"{EXECUTOR}.queue_agent_backup_job", _queue_backup)
        monkeypatch.setattr(f"{EXECUTOR}.dispatch_agent_job_best_effort", _dispatch)
        monkeypatch.setattr(f"{EXECUTOR}.wait_for_agent_backup_job", _wait_backup)
        monkeypatch.setattr(f"{EXECUTOR}.notify_backup_job_finished", _notify)


async def _run(db, repository, params=None, ctx=None):
    load_default_executors()
    op = _operation(
        db, repository, params=params or {"executor": "agent", "archive_name": "a"}
    )
    ctx = ctx or FakeContext(db, op)
    outcome = await get_executor("backup")(ctx)
    db.expire_all()
    return outcome, BackupJobFacade(db, db.get(Operation, op.id))


@pytest.mark.asyncio
async def test_hooks_run_around_the_agent_backup(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "stop-db", "pre-backup")
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["stop-db", "backup", "start-db"]
    assert outcome.status == "completed"
    assert agent.envs["stop-db"]["BORG_UI_HOOK_TYPE"] == "pre-backup"
    assert agent.envs["start-db"]["BORG_UI_BACKUP_STATUS"] == "success"
    assert agent.envs["start-db"]["BORG_UI_REPOSITORY_ID"] == str(agent_repo.id)
    assert agent.envs["start-db"]["BORG_UI_JOB_ID"] == str(job.id)
    # the transport had ended the row: it is running again under the post
    # hook, so the repository's lane stays taken, and ends as it was
    assert agent.status_under == {"stop-db": "running", "start-db": "running"}
    assert job.status == "completed"
    assert job.completed_at == datetime(2026, 10, 8, 2)
    assert agent.notified == []
    executions = db.query(ScriptExecution).order_by(ScriptExecution.id).all()
    assert [(e.agent_script_name, e.stdout) for e in executions] == [
        ("stop-db", "stop-db out"),
        ("start-db", "start-db out"),
    ]
    executions = db.query(ScriptExecution).order_by(ScriptExecution.id).all()
    assert [(e.agent_script_name, e.status, e.operation_id) for e in executions] == [
        ("stop-db", "completed", job.id),
        ("start-db", "completed", job.id),
    ]


@pytest.mark.asyncio
async def test_hooks_run_in_execution_order(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "second", "pre-backup", order=2)
    _hook(db, agent_repo, "first", "pre-backup", order=1)
    agent = Agent(db, monkeypatch)

    await _run(db, agent_repo)

    assert agent.calls == ["first", "second", "backup"]


@pytest.mark.asyncio
async def test_a_failed_pre_hook_fails_the_backup_and_still_runs_post_hooks(
    db, agent_repo, monkeypatch
):
    agent_repo.continue_on_hook_failure = False
    _hook(db, agent_repo, "stop-db", "pre-backup", order=1)
    _hook(db, agent_repo, "snapshot", "pre-backup", order=2, continue_on_error=False)
    _hook(db, agent_repo, "start-db", "post-backup", custom_run_on="failure")
    _hook(db, agent_repo, "report-ok", "post-backup", custom_run_on="success")
    agent = Agent(db, monkeypatch, rc={"snapshot": 2})

    outcome, job = await _run(db, agent_repo)

    # the service stop-db stopped is started again (#1385's rule)
    assert agent.calls == ["stop-db", "snapshot", "start-db"]
    assert outcome.status == "failed"
    assert json.loads(job.error_message) == {
        "key": "backend.errors.service.preBackupHooksFailed",
        "params": {"failed": 1, "total": 2},
    }
    assert agent.notified == ["failed"]


@pytest.mark.asyncio
async def test_a_failed_cleanup_after_a_failed_pre_hook_is_reported_too(
    db, agent_repo, monkeypatch
):
    agent_repo.continue_on_hook_failure = False
    _hook(db, agent_repo, "snapshot", "pre-backup", continue_on_error=False)
    _hook(db, agent_repo, "start-db", "post-backup", continue_on_error=False)
    agent = Agent(db, monkeypatch, rc={"snapshot": 2, "start-db": 2})

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["snapshot", "start-db"]
    assert outcome.status == "failed"
    first, second = job.error_message.split("\n")
    assert json.loads(first)["key"] == "backend.errors.service.preBackupHooksFailed"
    assert json.loads(second)["key"] == (
        "backend.errors.service.postBackupHooksAlsoFailed"
    )
    assert agent.notified == ["failed"]


@pytest.mark.asyncio
async def test_an_error_inside_the_pre_hooks_still_runs_the_post_hooks(
    db, agent_repo, monkeypatch
):
    _hook(db, agent_repo, "stop-db", "pre-backup", order=1)
    _hook(db, agent_repo, "snapshot", "pre-backup", order=2)
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    agent.raise_on = {"snapshot"}

    with pytest.raises(RuntimeError):
        await _run(db, agent_repo)

    assert agent.calls == ["stop-db", "snapshot", "start-db"]
    assert agent.envs["start-db"]["BORG_UI_BACKUP_STATUS"] == "failure"
    # the broken hook's record is closed, not left running
    broken = db.query(ScriptExecution).filter_by(agent_script_name="snapshot").one()
    assert broken.status == "failed"
    assert "snapshot broke" in broken.error_message


@pytest.mark.asyncio
async def test_a_failed_pre_hook_with_continue_on_hook_failure_backs_up(
    db, agent_repo, monkeypatch
):
    agent_repo.continue_on_hook_failure = True
    _hook(db, agent_repo, "snapshot", "pre-backup", continue_on_error=False)
    agent = Agent(db, monkeypatch, rc={"snapshot": 2})

    outcome, _ = await _run(db, agent_repo)

    assert agent.calls == ["snapshot", "backup"]
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_a_continue_on_error_failure_is_a_warning(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "snapshot", "pre-backup")  # continue_on_error defaults on
    agent = Agent(db, monkeypatch, rc={"snapshot": 3})

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["snapshot", "backup"]
    assert outcome.status == "completed_with_warnings"
    message = json.loads(job.error_message)
    assert message["key"] == "backend.errors.service.repositoryHookWarnings"
    assert "'snapshot' failed with exit code 3" in message["params"]["warnings"]
    # the runner writes the outcome's message onto the row
    assert outcome.error_message == job.error_message
    # the transport notified the agent's success; the warning follows
    assert agent.notified == ["completed_with_warnings"]


@pytest.mark.asyncio
async def test_post_hooks_hear_the_warning_a_pre_hook_gave(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "snapshot", "pre-backup")  # continue_on_error
    _hook(db, agent_repo, "on-warning", "post-backup", custom_run_on="warning")
    _hook(db, agent_repo, "on-success", "post-backup", custom_run_on="success")
    agent = Agent(db, monkeypatch, rc={"snapshot": 3})

    outcome, _ = await _run(db, agent_repo)

    assert agent.calls == ["snapshot", "backup", "on-warning"]
    assert agent.envs["on-warning"]["BORG_UI_BACKUP_STATUS"] == "warning"
    assert outcome.status == "completed_with_warnings"


@pytest.mark.asyncio
async def test_return_code_one_is_a_warning(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "check", "pre-backup", continue_on_error=False)
    agent = Agent(db, monkeypatch, rc={"check": 1})

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["check", "backup"]
    assert outcome.status == "completed_with_warnings"
    assert "exit code 1 (warning)" in job.error_message


@pytest.mark.asyncio
async def test_skip_on_failure_skips_the_backup(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "leader-only", "pre-backup", skip_on_failure=True)
    _hook(db, agent_repo, "start-db", "post-backup")
    _hook(db, agent_repo, "report-ok", "post-backup", custom_run_on="success")
    agent = Agent(db, monkeypatch, rc={"leader-only": 2})

    outcome, job = await _run(db, agent_repo)

    # the skipping hook itself may have changed something: "always" undoes it
    assert agent.calls == ["leader-only", "start-db"]
    assert outcome.status == "skipped"
    assert outcome.skip_reason == "Skipped by 'leader-only'"


@pytest.mark.asyncio
async def test_a_skip_after_an_earlier_hook_runs_the_always_hooks(
    db, agent_repo, monkeypatch
):
    _hook(db, agent_repo, "stop-db", "pre-backup", order=1)
    _hook(db, agent_repo, "leader-only", "pre-backup", order=2, skip_on_failure=True)
    _hook(db, agent_repo, "start-db", "post-backup")
    _hook(db, agent_repo, "on-failure", "post-backup", custom_run_on="failure")
    agent = Agent(db, monkeypatch, rc={"leader-only": 2})

    outcome, _ = await _run(db, agent_repo)

    assert agent.calls == ["stop-db", "leader-only", "start-db"]
    assert agent.envs["start-db"]["BORG_UI_BACKUP_STATUS"] == "skipped"
    assert outcome.status == "skipped"


@pytest.mark.asyncio
async def test_a_skip_whose_cleanup_fails_is_a_failure(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "stop-db", "pre-backup", order=1)
    _hook(db, agent_repo, "leader-only", "pre-backup", order=2, skip_on_failure=True)
    _hook(db, agent_repo, "start-db", "post-backup", continue_on_error=False)
    agent = Agent(db, monkeypatch, rc={"leader-only": 2, "start-db": 2})

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["stop-db", "leader-only", "start-db"]
    assert outcome.status == "failed"
    assert json.loads(job.error_message)["key"] == (
        "backend.errors.service.postBackupHooksAlsoFailed"
    )
    assert agent.notified == ["failed"]


@pytest.mark.asyncio
async def test_a_failed_post_hook_fails_a_completed_backup(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "start-db", "post-backup", continue_on_error=False)
    agent = Agent(db, monkeypatch, rc={"start-db": 2})
    chained = []
    monkeypatch.setattr(
        f"{EXECUTOR}._enqueue_post_create_chain", lambda ctx, op: chained.append(op.id)
    )

    outcome, job = await _run(db, agent_repo)

    assert outcome.status == "failed"
    assert json.loads(job.error_message)["key"] == (
        "backend.errors.service.postBackupHooksFailed"
    )
    # the archive exists: its index chain is enqueued all the same
    assert chained == [job.id]
    assert agent.notified == ["failed"]


@pytest.mark.asyncio
async def test_post_hooks_follow_a_failed_backup(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "on-failure", "post-backup", custom_run_on="failure")
    _hook(db, agent_repo, "on-success", "post-backup", custom_run_on="success", order=2)
    _hook(db, agent_repo, "always", "post-backup", order=3, continue_on_error=False)
    agent = Agent(db, monkeypatch, rc={"always": 2}, backup="failed")

    def _fail(session, agent_job_id, backup_job_id, is_cancelled, **kw):
        job = BackupJobFacade(db, db.get(Operation, backup_job_id))
        job.status = "failed"
        job.error_message = json.dumps({"key": "backend.errors.borg.unknownError"})
        db.commit()

    async def _wait_backup(*args, **kw):
        _fail(*args, **kw)
        return "failed"

    monkeypatch.setattr(f"{EXECUTOR}.wait_for_agent_backup_job", _wait_backup)

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["backup", "on-failure", "always"]
    assert agent.envs["always"]["BORG_UI_BACKUP_STATUS"] == "failure"
    assert outcome.status == "failed"
    assert "postBackupHooksAlsoFailed" in job.error_message


@pytest.mark.asyncio
async def test_an_error_after_the_pre_hooks_runs_the_post_hooks(
    db, agent_repo, monkeypatch
):
    _hook(db, agent_repo, "stop-db", "pre-backup")
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    agent.queue_error = HTTPException(status_code=409, detail="busy")

    with pytest.raises(HTTPException):
        await _run(db, agent_repo)

    assert agent.calls == ["stop-db", "start-db"]
    assert agent.envs["start-db"]["BORG_UI_BACKUP_STATUS"] == "failure"


@pytest.mark.asyncio
async def test_a_failing_cleanup_does_not_hide_the_error(db, agent_repo, monkeypatch):
    """The busy repository's 409 still reaches the runner, which defers on
    it, when the cleanup hook after it breaks."""
    _hook(db, agent_repo, "stop-db", "pre-backup")
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    agent.queue_error = HTTPException(status_code=409, detail="busy")
    agent.raise_on = {"start-db"}

    with pytest.raises(HTTPException) as raised:
        await _run(db, agent_repo)

    assert raised.value.status_code == 409
    assert agent.calls == ["stop-db", "start-db"]


@pytest.mark.asyncio
async def test_a_busy_repository_defers_before_any_hook(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "stop-db", "pre-backup")
    agent = Agent(db, monkeypatch)

    def _busy(*args, **kwargs):
        raise HTTPException(status_code=409, detail="busy")

    monkeypatch.setattr(f"{EXECUTOR}.ensure_repository_admission", _busy)

    with pytest.raises(HTTPException):
        await _run(db, agent_repo)

    assert agent.calls == []


@pytest.mark.asyncio
async def test_skip_hooks_runs_none(db, agent_repo, monkeypatch):
    """A plan that does not run repository scripts (`skip_hooks`)."""
    _hook(db, agent_repo, "stop-db", "pre-backup")
    agent_repo.pre_backup_script = "systemctl stop db"
    db.commit()
    agent = Agent(db, monkeypatch)

    outcome, _ = await _run(
        db,
        agent_repo,
        params={"executor": "agent", "archive_name": "a", "skip_hooks": True},
    )

    assert agent.calls == ["backup"]
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_a_resumed_backup_runs_no_pre_hook_again(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "stop-db", "pre-backup")
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    monkeypatch.setattr(
        f"{EXECUTOR}.get_agent_job_for_backup",
        lambda session, job: SimpleNamespace(id=77, status="running"),
    )

    await _run(db, agent_repo)

    assert agent.calls == ["backup", "start-db"]


@pytest.mark.asyncio
async def test_a_cancel_during_the_pre_hooks_runs_the_post_hooks(
    db, agent_repo, monkeypatch
):
    _hook(db, agent_repo, "stop-db", "pre-backup")
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    load_default_executors()
    op = _operation(db, agent_repo, params={"executor": "agent", "archive_name": "a"})
    ctx = FakeContext(db, op)

    async def _wait_and_cancel(session, agent_job_id, *, is_cancelled, timeout_seconds):
        agent.calls.append("stop-db")
        ctx._cancelled = True
        return {"status": "canceled", "result": {}, "error_message": "canceled"}

    monkeypatch.setattr(f"{HOOKS}.wait_for_agent_script_job", _wait_and_cancel)

    outcome = await get_executor("backup")(ctx)

    assert "backup" not in agent.calls
    assert outcome.status == "failed"
    assert db.get(Operation, op.id).status == "cancelled"
    # the post-backup hook ran (it went through the patched waiter too)
    assert agent.calls == ["stop-db", "stop-db"]


@pytest.mark.asyncio
async def test_a_raising_post_hook_after_a_cancel_keeps_the_cancel(
    db, agent_repo, monkeypatch
):
    _hook(db, agent_repo, "stop-db", "pre-backup")
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    load_default_executors()
    op = _operation(db, agent_repo, params={"executor": "agent", "archive_name": "a"})
    ctx = FakeContext(db, op)

    async def _wait(session, agent_job_id, *, is_cancelled, timeout_seconds):
        if ctx._cancelled:
            raise RuntimeError("start-db broke")
        ctx._cancelled = True
        return {"status": "completed", "result": {"return_code": 0}}

    monkeypatch.setattr(f"{HOOKS}.wait_for_agent_script_job", _wait)

    outcome = await get_executor("backup")(ctx)

    assert outcome.status == "failed"
    assert db.get(Operation, op.id).status == "cancelled"


@pytest.mark.asyncio
async def test_a_raising_post_hook_fails_a_completed_backup(
    db, agent_repo, monkeypatch
):
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    agent.raise_on = {"start-db"}

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["backup", "start-db"]
    assert outcome.status == "failed"
    assert json.loads(job.error_message) == {
        "key": "backend.errors.service.postBackupHooksFailed",
        "params": {"failed": 1, "total": 1},
    }
    assert agent.notified == ["failed"]


@pytest.mark.asyncio
async def test_a_raising_cleanup_after_a_skip_is_a_failure(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "leader-only", "pre-backup", skip_on_failure=True)
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch, rc={"leader-only": 2})
    agent.raise_on = {"start-db"}

    outcome, job = await _run(db, agent_repo)

    assert outcome.status == "failed"
    assert json.loads(job.error_message)["key"] == (
        "backend.errors.service.postBackupHooksAlsoFailed"
    )


@pytest.mark.asyncio
async def test_a_cancel_before_any_hook_runs_no_post_hook(db, agent_repo, monkeypatch):
    _hook(db, agent_repo, "start-db", "post-backup")
    agent = Agent(db, monkeypatch)
    load_default_executors()
    op = _operation(db, agent_repo, params={"executor": "agent", "archive_name": "a"})
    ctx = FakeContext(db, op)
    ctx._cancelled = True

    outcome = await get_executor("backup")(ctx)

    assert agent.calls == []
    assert outcome.status == "failed"
    assert db.get(Operation, op.id).status == "cancelled"


@pytest.mark.asyncio
async def test_scripts_the_agent_cannot_run_are_reported(db, agent_repo, monkeypatch):
    agent_repo.pre_backup_script = "systemctl stop postgresql"
    script = Script(name="stop-db", file_path="library/stop-db.sh", category="custom")
    db.add(script)
    db.flush()
    db.add(
        RepositoryScript(
            repository_id=agent_repo.id, script_id=script.id, hook_type="post-backup"
        )
    )
    db.commit()
    agent = Agent(db, monkeypatch)

    outcome, job = await _run(db, agent_repo)

    assert agent.calls == ["backup"]
    assert outcome.status == "completed_with_warnings"
    assert json.loads(job.error_message) == {
        "key": "backend.errors.service.agentRepositoryScriptsNotRun",
        "params": {
            "scripts": "pre-backup inline script, post-backup library script 'stop-db'"
        },
    }
    assert agent.notified == ["completed_with_warnings"]


@pytest.mark.asyncio
async def test_unrunnable_scripts_and_a_hook_warning_are_both_reported(
    db, agent_repo, monkeypatch
):
    agent_repo.pre_backup_script = "systemctl stop postgresql"
    db.commit()
    _hook(db, agent_repo, "check", "pre-backup")
    agent = Agent(db, monkeypatch, rc={"check": 1})

    outcome, job = await _run(db, agent_repo)

    assert outcome.status == "completed_with_warnings"
    keys = [json.loads(line)["key"] for line in job.error_message.split("\n")]
    assert keys == [
        "backend.errors.service.agentRepositoryScriptsNotRun",
        "backend.errors.service.repositoryHookWarnings",
    ]


@pytest.mark.asyncio
async def test_server_hooks_leave_agent_scripts_alone(db, repository):
    _hook(db, repository, "stop-db", "pre-backup")

    result = await ScriptLibraryExecutor(db).execute_hooks(
        repository_id=repository.id, hook_type="pre-backup"
    )

    assert result["scripts_executed"] == 0
    assert result["success"] is True
