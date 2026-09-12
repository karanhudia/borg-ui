"""A plan's agent hook must reach the agent, and must not be mistaken for
the backup it runs beside.

Phase 9 dropped `agent_jobs.backup_job_id`; `queue_agent_script_job` kept
passing it and raised `TypeError` at construction, so every agent pre/post
backup hook failed at once. A pre-backup hook that cannot be queued aborts
the plan run before the backup, which is what makes this worth pinning.

The column it was tempting to move the link to, `operation_id`, is the one
every reader treats as "this agent job *is* that operation": a script row
wearing it would let a failing hook fail a finished backup. So a script job
carries no backup link at all, and the lookups that want the backup's
transport job say so.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Repository, ScriptExecution
from app.services.backup_plan_execution_service import BackupPlanExecutionService
from app.services.operations.backup_facade import create_backup_operation
from app.services.repository_executor import (
    BACKUP_AGENT_JOB_TYPE,
    SCRIPT_RUN_CAPABILITY,
    get_agent_job_for_backup,
    queue_agent_script_job,
)


@pytest.fixture()
def agent(db_session):
    machine = AgentMachine(
        name="Agent",
        agent_id="agt_queue_script",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-se",
        status="online",
        capabilities=[SCRIPT_RUN_CAPABILITY],
    )
    db_session.add(machine)
    db_session.commit()
    return machine


def _agent_repository(db_session, agent, name="nas"):
    repository = Repository(
        name=name,
        path=f"/repos/{name}",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=agent.id,
    )
    db_session.add(repository)
    db_session.commit()
    return repository


@pytest.mark.unit
def test_script_job_is_queued_and_carries_no_backup_link(db_session, agent):
    job = queue_agent_script_job(
        db_session, agent, script_name="pre-db-dump.sh", env={"A": "b"}
    )

    assert job.id is not None
    assert job.job_type == "script"
    assert job.status == "queued"
    assert job.payload["job_kind"] == "script.run"
    # the link column means "transport job of this operation"; a hook is not that
    assert job.operation_id is None


@pytest.mark.unit
def test_the_transport_job_wins_over_a_script_row_of_the_same_run(db_session, agent):
    """`get_agent_job_for_backup` drives the backup: it cancels that job,
    reads its logs and takes the backup's outcome from its status. A row
    that merely shares the operation must never be handed back, not even
    when it is the newer one."""
    repository = _agent_repository(db_session, agent)
    backup = create_backup_operation(
        db_session, repository, trigger="plan", executor="agent"
    )
    transport = AgentJob(
        agent_machine_id=agent.id,
        operation_id=backup.id,
        # the constant the writers use, so a rename cannot part reader
        # from writer without this test noticing
        job_type=BACKUP_AGENT_JOB_TYPE,
        status="running",
        payload={"schema_version": 1, "job_kind": "backup.create"},
    )
    db_session.add(transport)
    db_session.commit()
    impostor = AgentJob(
        agent_machine_id=agent.id,
        operation_id=backup.id,
        job_type="script",
        status="queued",
        payload={"schema_version": 1, "job_kind": "script.run"},
    )
    db_session.add(impostor)
    db_session.commit()

    assert impostor.id > transport.id
    assert get_agent_job_for_backup(db_session, backup).id == transport.id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_plan_hook_gets_past_queueing_and_records_its_execution(
    db_session, agent, monkeypatch
):
    """The caller the regression actually broke: the plan's hook step. It
    must queue the job, keep a `ScriptExecution` for it and report success
    to the run, instead of dying in `AgentJob(...)`."""
    from app.services import backup_plan_execution_service as module

    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    service = BackupPlanExecutionService()
    monkeypatch.setattr(
        service, "_resolve_plan_agent", lambda db, plan_id: (agent, None)
    )
    monkeypatch.setattr(
        service, "_build_agent_script_env", lambda *a, **k: {"BORG_UI_RUN_ID": "1"}
    )
    context = SimpleNamespace(plan_id=7)

    with (
        patch.object(module, "dispatch_agent_job_best_effort", new=AsyncMock()),
        patch.object(
            module,
            "wait_for_agent_script_job",
            new=AsyncMock(
                return_value={"status": "completed", "result": {"return_code": 0}}
            ),
        ),
    ):
        ok, error = await service._execute_agent_plan_script(
            run_id=1,
            context=context,
            hook_type="pre-backup",
            backup_result=None,
            agent_script_name="pre-db-dump.sh",
        )

    assert (ok, error) == (True, None)
    queued = db_session.query(AgentJob).filter(AgentJob.job_type == "script").all()
    assert len(queued) == 1
    assert queued[0].operation_id is None
    execution = db_session.query(ScriptExecution).one()
    assert execution.agent_script_name == "pre-db-dump.sh"
    assert execution.status == "completed"
    # what replaces the link this change removed: the execution points at
    # the job, which is how the activity feed streams a running hook's output
    assert execution.agent_job_id == queued[0].id
