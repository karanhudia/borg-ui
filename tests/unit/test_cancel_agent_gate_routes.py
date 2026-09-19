"""Every route that cancels a running job refuses one whose managed agent
would not stop Borg (before 0.1.7), not only the activity route (#1078)."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation, Repository
from app.services.operations.enqueue import enqueue
from app.services.operations.runner import operation_runner
from tests.utils.operations import seed_job_operation


def _old_agent_repo(test_db):
    agent = AgentMachine(
        name="gate-agent",
        agent_id="agt_gate",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=["repository.check", "backup.create"],
    )
    test_db.add(agent)
    test_db.commit()
    repo = Repository(
        name="gate-repo",
        path="/agent/gate",
        encryption="none",
        compression="lz4",
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=agent.id,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
def test_the_operations_cancel_refuses_a_check_an_old_agent_runs(
    test_client, test_db, admin_headers
):
    repo = _old_agent_repo(test_db)
    op = enqueue(test_db, "check", repository_id=repo.id)
    op.status = "running"
    test_db.commit()

    with (
        patch.dict(operation_runner.running_tasks, {op.id: object()}),
        patch(
            "app.api.operations.operation_runner.request_cancel",
            new=AsyncMock(return_value=True),
        ) as request_cancel,
    ):
        response = test_client.post(
            f"/api/operations/{op.id}/cancel", headers=admin_headers
        )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.activity.cannotCancelWhileRunning"
    )
    request_cancel.assert_not_awaited()


@pytest.mark.unit
def test_the_backup_cancel_refuses_a_backup_an_old_agent_runs(
    test_client, test_db, admin_headers
):
    repo = _old_agent_repo(test_db)
    job = seed_job_operation(
        test_db,
        "backup",
        repository_id=repo.id,
        status="running",
        started_at=datetime.utcnow(),
        execution_mode="agent",
    )
    test_db.commit()
    agent_job = AgentJob(
        agent_machine_id=repo.agent_machine_id,
        job_type="backup",
        operation_id=job.id,
        status="running",
        payload={"job_kind": "backup.create"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(agent_job)
    test_db.commit()

    response = test_client.post(f"/api/backup/cancel/{job.id}", headers=admin_headers)

    assert response.status_code == 409
    test_db.expire_all()
    assert test_db.get(AgentJob, agent_job.id).status == "running"
    assert test_db.get(Operation, job.id).status == "running"


@pytest.mark.unit
def test_an_unknown_activity_type_is_rejected(test_client, admin_headers):
    response = test_client.post(
        "/api/activity/no_such_kind/1/cancel", headers=admin_headers
    )

    assert response.status_code == 400
    assert response.json()["detail"]["key"] == "backend.errors.activity.invalidJobType"


@pytest.mark.unit
def test_a_refused_operations_cancel_leaves_the_queued_agent_job_alone(
    test_client, test_db, admin_headers
):
    """The runner does not own the task (another worker's, or left running
    across a restart): the cancel is refused before the agent gate could
    take the queued agent job off the queue."""
    repo = _old_agent_repo(test_db)
    op = enqueue(test_db, "check", repository_id=repo.id)
    op.status = "running"
    test_db.commit()
    agent_job = AgentJob(
        agent_machine_id=repo.agent_machine_id,
        job_type="repository",
        status="queued",
        payload={
            "job_kind": "repository.check",
            "operation": {"maintenance_job": {"kind": "check", "id": op.id}},
        },
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(agent_job)
    test_db.commit()

    response = test_client.post(
        f"/api/operations/{op.id}/cancel", headers=admin_headers
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.activity.cannotCancelWhileRunning"
    )
    test_db.expire_all()
    assert test_db.get(AgentJob, agent_job.id).status == "queued"
    assert test_db.get(Operation, op.id).status == "running"


@pytest.mark.unit
def test_the_operations_cancel_refuses_a_running_kind_that_does_not_stop(
    test_client, test_db, admin_headers
):
    repo = Repository(
        name="stats-repo", path="/repo/stats", encryption="none", compression="lz4"
    )
    test_db.add(repo)
    test_db.commit()
    op = enqueue(test_db, "stats", repository_id=repo.id)
    op.status = "running"
    test_db.commit()

    with patch.dict(operation_runner.running_tasks, {op.id: object()}):
        response = test_client.post(
            f"/api/operations/{op.id}/cancel", headers=admin_headers
        )

    assert response.status_code == 409
    test_db.expire_all()
    assert test_db.get(Operation, op.id).status == "running"
