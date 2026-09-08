import pytest
from fastapi import HTTPException

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Repository
from app.services.job_admission import (
    AGENT_JOB_KIND_OPERATIONS,
    OPERATION_BACKUP,
    OPERATION_BREAK_LOCK,
    OPERATION_CLASS_REPOSITORY_READ,
    OPERATION_CLASS_REPOSITORY_WRITE,
    OPERATION_RCLONE_SYNC,
    ensure_repository_admission,
    operation_class_for,
    operation_for_agent_job_kind,
)


@pytest.mark.unit
def test_break_lock_is_a_write_operation():
    # break-lock forcibly removes the repo lock, so it must conflict with ANY
    # active borg work (reads hold locks too), not share the READ bucket.
    assert operation_class_for(OPERATION_BREAK_LOCK) == OPERATION_CLASS_REPOSITORY_WRITE


@pytest.mark.unit
def test_repository_admission_rejects_active_agent_repository_job(db_session):
    agent = AgentMachine(
        name="Agent",
        agent_id="agt_repo_work",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
    )
    repo = Repository(
        name="Repo",
        path="/repos/agent-work",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=1,
    )
    db_session.add_all([agent, repo])
    db_session.flush()
    repo.agent_machine_id = agent.id
    db_session.add(
        AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status="queued",
            payload={
                "schema_version": 1,
                "job_kind": "repository.info",
                "repository": {"id": repo.id, "path": repo.path},
            },
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repo, OPERATION_BACKUP)

    assert exc.value.status_code == 409
    assert exc.value.detail["key"] == "backend.errors.jobs.repositoryOperationActive"
    assert exc.value.detail["params"]["active_operation"] == "repository.info"
    assert exc.value.detail["params"]["active_status"] == "queued"


@pytest.mark.unit
def test_break_lock_fails_closed_against_unknown_active_repository_job(db_session):
    # An active repository agent job whose kind we don't recognize might still
    # hold a borg lock, so break_lock must be blocked (fail closed), not allowed.
    agent = AgentMachine(
        name="Agent",
        agent_id="agt_unknown_kind",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
    )
    repo = Repository(
        name="Repo",
        path="/repos/agent-unknown",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=1,
    )
    db_session.add_all([agent, repo])
    db_session.flush()
    repo.agent_machine_id = agent.id
    db_session.add(
        AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status="running",
            payload={
                "schema_version": 1,
                "job_kind": "repository.some_future_kind",
                "repository": {"id": repo.id, "path": repo.path},
            },
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repo, OPERATION_BREAK_LOCK)

    assert exc.value.status_code == 409


@pytest.mark.unit
def test_rclone_sync_is_mapped_and_classed_as_a_read():
    # Without the mapping, operation_for_agent_job_kind() raises and every
    # cloud mirror on an agent repository is rejected at admission with
    # "Unsupported agent repository operation: repository.rclone_sync",
    # never reaching the agent that supports it.
    assert AGENT_JOB_KIND_OPERATIONS["repository.rclone_sync"] == OPERATION_RCLONE_SYNC
    assert (
        operation_for_agent_job_kind("repository.rclone_sync") == OPERATION_RCLONE_SYNC
    )
    # rclone reads the repository and writes only to the remote. It also has
    # to be in one of the two sets: operation_class_for() raises on an
    # operation it cannot classify, so the mapping alone would still fail.
    assert operation_class_for(OPERATION_RCLONE_SYNC) == OPERATION_CLASS_REPOSITORY_READ


def test_break_lock_is_refused_while_a_check_operation_runs(db_session):
    """Phase 5 moved check into `operations`. Admission must still see it, or
    break_lock would tear the lock out from under a running borg check."""
    from app.database.models import Operation

    repo = Repository(
        name="Repo",
        path="/repos/check-operation",
        encryption="none",
        repository_type="local",
    )
    db_session.add(repo)
    db_session.flush()
    db_session.add(
        Operation(
            repository_id=repo.id,
            kind="check",
            category="maintenance",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-admission",
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_repository_admission(db_session, repo, OPERATION_BREAK_LOCK)

    assert exc.value.status_code == 409
    params = exc.value.detail["params"]
    assert params["active_operation"] == "check"
    assert params["active_job_table"] == "operations"
    # The payload keeps the legacy vocabulary readers already understand.
    assert params["active_status"] == "running"


def test_a_queued_check_operation_reports_the_legacy_pending_word(db_session):
    from app.database.models import Operation
    from app.services.job_admission import list_active_repository_work

    repo = Repository(
        name="Repo",
        path="/repos/queued-check",
        encryption="none",
        repository_type="local",
    )
    db_session.add(repo)
    db_session.flush()
    db_session.add(
        Operation(
            repository_id=repo.id,
            kind="check",
            category="maintenance",
            status="queued",
            trigger="manual",
            priority=0,
            run_id="run-queued",
        )
    )
    db_session.commit()

    work = list_active_repository_work(db_session, repo)

    assert [(w.operation, w.status) for w in work] == [("check", "pending")]


def test_a_running_wipe_operation_is_active_repository_work(db_session):
    """Phase 6: wipe moved to `operations`, so admission must see it there."""
    from app.database.models import Operation
    from app.services.job_admission import list_active_repository_work

    repo = Repository(
        name="Repo",
        path="/repos/running-wipe",
        encryption="none",
        repository_type="local",
    )
    db_session.add(repo)
    db_session.flush()
    db_session.add(
        Operation(
            repository_id=repo.id,
            kind="wipe",
            category="maintenance",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-wipe",
        )
    )
    db_session.commit()

    work = list_active_repository_work(db_session, repo)

    assert [(w.operation, w.status) for w in work] == [("repository_wipe", "running")]
