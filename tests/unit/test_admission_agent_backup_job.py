"""Admission while the agent job of an earlier backup has not ended."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation, Repository
from app.services.job_admission import (
    OPERATION_BACKUP,
    OPERATION_BREAK_LOCK,
    OPERATION_PRUNE,
    ensure_repository_admission,
)
from app.services.operations.backup_facade import admission_ignore_for
from app.services.operations.runner import OperationRunner


def _agent_backup(db, *, operation_status, agent_job_status):
    """A backup of an agent's repository: its row and the agent job that
    carries it."""
    agent = AgentMachine(
        name="Agent",
        agent_id="agt_backup_admission",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
        capabilities=["jobs.cancel"],
    )
    db.add(agent)
    db.flush()
    repository = Repository(
        name="Repo",
        path="ssh://host/./repo",
        encryption="none",
        repository_type="ssh",
        executor_type="agent",
        agent_machine_id=agent.id,
    )
    db.add(repository)
    db.flush()
    operation = Operation(
        repository_id=repository.id,
        kind="backup",
        category="backup",
        status=operation_status,
        trigger="plan",
        priority=0,
        run_id="run-1",
        execution_mode="agent",
        params={"executor": "agent", "archive_name": "a-1"},
    )
    db.add(operation)
    db.flush()
    now = datetime.now(timezone.utc)
    agent_job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status=agent_job_status,
        operation_id=operation.id,
        payload={
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {
                "id": repository.id,
                "path": repository.path,
                "borg_version": 1,
            },
            "backup": {"archive_name": "a-1", "source_paths": ["/data"]},
        },
        claimed_at=now,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(agent_job)
    db.commit()
    return repository, operation, agent_job


@pytest.mark.unit
@pytest.mark.parametrize("agent_job_status", ["cancel_requested", "running"])
def test_a_backup_is_refused_while_the_cancelled_backups_agent_job_is_live(
    db_session, agent_job_status
):
    # The backup's row is closed, the agent has not reported the end of its
    # Borg process: the repository lock may still be held.
    repository, _, agent_job = _agent_backup(
        db_session, operation_status="cancelled", agent_job_status=agent_job_status
    )

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repository, OPERATION_BACKUP)

    assert exc.value.status_code == 409
    params = exc.value.detail["params"]
    assert params["active_job_table"] == "agent_jobs"
    assert params["active_job_id"] == agent_job.id
    assert params["active_status"] == agent_job_status


@pytest.mark.unit
def test_a_backup_is_refused_after_a_restart_while_the_agent_still_runs_the_last(
    db_session,
):
    repository, operation, agent_job = _agent_backup(
        db_session, operation_status="running", agent_job_status="running"
    )

    OperationRunner().recover_on_startup(db_session)
    db_session.refresh(operation)
    db_session.refresh(agent_job)
    assert operation.status == "failed"
    assert agent_job.status == "running"

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repository, OPERATION_BACKUP)

    assert exc.value.status_code == 409
    assert exc.value.detail["params"]["active_job_id"] == agent_job.id


@pytest.mark.unit
def test_a_prune_is_refused_while_the_backups_agent_job_is_live(db_session):
    repository, _, agent_job = _agent_backup(
        db_session, operation_status="failed", agent_job_status="running"
    )

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repository, OPERATION_PRUNE)

    assert exc.value.status_code == 409
    assert exc.value.detail["params"]["active_operation"] == OPERATION_BACKUP
    assert exc.value.detail["params"]["active_job_id"] == agent_job.id


@pytest.mark.unit
@pytest.mark.parametrize(
    "agent_job_status", ["completed", "completed_with_warnings", "failed", "canceled"]
)
def test_a_backup_is_admitted_once_the_agent_reported_the_end(
    db_session, agent_job_status
):
    repository, _, _ = _agent_backup(
        db_session, operation_status="cancelled", agent_job_status=agent_job_status
    )

    ensure_repository_admission(db_session, repository, OPERATION_BACKUP)


@pytest.mark.unit
def test_a_backup_is_not_refused_by_its_own_agent_job(db_session):
    # As before the job counted: a backup that leaves its own row out of the
    # check is not held up by the job that carries that row.
    repository, operation, _ = _agent_backup(
        db_session, operation_status="queued", agent_job_status="queued"
    )

    ensure_repository_admission(
        db_session,
        repository,
        OPERATION_BACKUP,
        ignore=admission_ignore_for(operation),
    )


@pytest.mark.unit
def test_another_operation_is_refused_by_the_backups_agent_job(db_session):
    repository, operation, agent_job = _agent_backup(
        db_session, operation_status="failed", agent_job_status="running"
    )
    other = Operation(
        repository_id=repository.id,
        kind="backup",
        category="backup",
        status="queued",
        trigger="plan",
        priority=0,
        run_id="run-2",
        execution_mode="agent",
        params={"executor": "agent", "archive_name": "a-2"},
    )
    db_session.add(other)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(
            db_session,
            repository,
            OPERATION_BACKUP,
            ignore=admission_ignore_for(other),
        )

    assert exc.value.detail["params"]["active_job_table"] == "agent_jobs"
    assert exc.value.detail["params"]["active_job_id"] == agent_job.id


@pytest.mark.unit
def test_another_repositorys_backup_is_not_refused(db_session):
    repository, _, _ = _agent_backup(
        db_session, operation_status="cancelled", agent_job_status="running"
    )
    other = Repository(
        name="Other",
        path="ssh://host/./other",
        encryption="none",
        repository_type="ssh",
        executor_type="agent",
        agent_machine_id=repository.agent_machine_id,
    )
    db_session.add(other)
    db_session.commit()

    ensure_repository_admission(db_session, other, OPERATION_BACKUP)


def _direct_backup_job(db, agent_machine_id, path):
    """A backup submitted for an agent directly: no operation, no
    repository id."""
    now = datetime.now(timezone.utc)
    job = AgentJob(
        agent_machine_id=agent_machine_id,
        job_type="backup",
        status="running",
        payload={
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {"path": path, "borg_version": 1},
            "backup": {"archive_name": "a-1", "source_paths": ["/data"]},
        },
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return job


@pytest.mark.unit
def test_a_backup_without_a_repository_id_is_matched_by_its_path(db_session):
    repository, _, _ = _agent_backup(
        db_session, operation_status="completed", agent_job_status="completed"
    )
    job = _direct_backup_job(db_session, repository.agent_machine_id, repository.path)

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repository, OPERATION_BREAK_LOCK)

    assert exc.value.detail["params"]["active_job_id"] == job.id
