"""An agent hook's exit code is the hook's, not Borg's (#1389).

A ``script.run`` job reports the script's return code with its stdout and
stderr. The agent-script contract reads that code as 0 success, 1 warning
(the backup proceeds), >1 failure. Read with Borg's rules instead, a
warning stored the job ``completed_with_warnings``, which the hook
classifier took for a failure, and a failure went through the failure
path, which keeps only the return code: the script's output was lost.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.agents import _complete_agent_job
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, ScriptExecution
from app.services.backup_plan_execution_service import BackupPlanExecutionService
from app.services.repository_executor import (
    SCRIPT_AGENT_JOB_TYPE,
    SCRIPT_RUN_CAPABILITY,
)


@pytest.fixture()
def agent(db_session):
    machine = AgentMachine(
        name="Agent",
        agent_id="agt_script_completion",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-se",
        status="online",
        capabilities=[SCRIPT_RUN_CAPABILITY],
    )
    db_session.add(machine)
    db_session.commit()
    return machine


def _running_job(db_session, agent, job_type, job_kind):
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type=job_type,
        status="running",
        payload={"schema_version": 1, "job_kind": job_kind},
    )
    db_session.add(job)
    db_session.commit()
    return job


def _script_result(return_code):
    return {"return_code": return_code, "stdout": "dump out", "stderr": "denied"}


@pytest.mark.unit
@pytest.mark.parametrize("return_code", [0, 1, 2, 101, -9])
def test_a_script_job_completes_with_its_report_intact(db_session, agent, return_code):
    job = _running_job(db_session, agent, SCRIPT_AGENT_JOB_TYPE, "script.run")

    assert _complete_agent_job(job, db_session, result=_script_result(return_code))
    db_session.commit()

    db_session.expire_all()
    stored = db_session.get(AgentJob, job.id)
    assert stored.status == "completed"
    assert stored.result == _script_result(return_code)
    assert stored.error_message is None


@pytest.mark.unit
def test_a_script_job_with_a_malformed_return_code_still_fails_closed(
    db_session, agent
):
    job = _running_job(db_session, agent, SCRIPT_AGENT_JOB_TYPE, "script.run")

    assert _complete_agent_job(
        job, db_session, result={"return_code": "1", "stdout": "", "stderr": ""}
    )
    db_session.commit()

    db_session.expire_all()
    assert db_session.get(AgentJob, job.id).status == "failed"


@pytest.mark.unit
@pytest.mark.parametrize(
    "return_code, status, result",
    [
        (0, "completed", {"return_code": 0, "stdout": "x"}),
        (1, "completed_with_warnings", {"return_code": 1, "stdout": "x"}),
        (2, "failed", {"return_code": 2}),
    ],
)
def test_a_borg_job_keeps_borgs_exit_code_rules(
    db_session, agent, return_code, status, result
):
    job = _running_job(db_session, agent, "repository", "repository.list")

    assert _complete_agent_job(
        job, db_session, result={"return_code": return_code, "stdout": "x"}
    )
    db_session.commit()

    db_session.expire_all()
    stored = db_session.get(AgentJob, job.id)
    assert stored.status == status
    assert {k: stored.result.get(k) for k in result} == result
    if status == "failed":
        assert "stdout" not in stored.result


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "return_code, hook_ok, execution_status",
    [(0, True, "completed"), (1, True, "warning"), (2, False, "failed")],
)
async def test_the_plan_hook_reads_the_agents_report_by_the_script_contract(
    db_session, agent, monkeypatch, return_code, hook_ok, execution_status
):
    """The whole way through: the plan queues the hook, the agent reports
    through the server's completion path, and the hook's record carries the
    verdict the contract gives plus the script's own output."""
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

    async def agent_runs_the_script(db, agent_job):
        _complete_agent_job(agent_job, db, result=_script_result(return_code))
        db.commit()

    with patch.object(
        module,
        "dispatch_agent_job_best_effort",
        new=AsyncMock(side_effect=agent_runs_the_script),
    ):
        ok, message = await service._execute_agent_plan_script(
            run_id=1,
            context=SimpleNamespace(plan_id=7),
            hook_type="pre-backup",
            backup_result=None,
            agent_script_name="pre-db-dump.sh",
        )

    assert ok is hook_ok
    execution = db_session.query(ScriptExecution).one()
    assert execution.status == execution_status
    assert execution.exit_code == return_code
    assert execution.stdout == "dump out"
    assert execution.stderr == "denied"
    if return_code:
        assert f"exit code {return_code}" in message
        assert "borg" not in message
    else:
        assert message is None
