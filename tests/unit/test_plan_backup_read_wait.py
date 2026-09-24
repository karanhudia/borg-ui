"""A plan's backup waits out read work instead of failing the repository.

The history index runs `repository.diff` as an agent job, which admission
counts as read work on the repository. A plan backup arriving meanwhile
used to be refused with 409 and marked that repository failed. It now
waits for the read work, bounded, and only the refusal that outlives the
budget fails the repository (issue #1102).
"""

import asyncio
import time

import pytest
from fastapi import HTTPException

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Operation, Repository
from app.services.job_admission import (
    OPERATION_BACKUP,
    READ_WORK_ADMITTED,
    READ_WORK_CANCELLED,
    admit_repository_with_read_work_wait,
)


def _agent_repository(db_session, name: str):
    agent = AgentMachine(
        name=f"agent-{name}",
        agent_id=f"agt_{name}",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
    )
    repo = Repository(
        name=name,
        path=f"/repos/{name}",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        agent_machine_id=1,
    )
    db_session.add_all([agent, repo])
    db_session.flush()
    repo.agent_machine_id = agent.id
    db_session.commit()
    return agent, repo


def _agent_job(db_session, agent, repo, *, kind="repository.diff"):
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="running",
        payload={
            "schema_version": 1,
            "job_kind": kind,
            "repository": {"id": repo.id, "path": repo.path},
        },
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backup_waits_for_a_running_diff_and_then_runs(db_session):
    agent, repo = _agent_repository(db_session, "diffing")
    job = _agent_job(db_session, agent, repo)

    async def _finish_diff():
        await asyncio.sleep(0.05)
        job.status = "completed"
        db_session.commit()

    finisher = asyncio.ensure_future(_finish_diff())
    outcome = await admit_repository_with_read_work_wait(
        db_session,
        repo,
        OPERATION_BACKUP,
        timeout_seconds=5,
        transient_only=False,
        poll_interval_seconds=0.01,
        retry_pause_seconds=0.0,
    )
    await finisher

    assert outcome == READ_WORK_ADMITTED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_diff_that_outlives_the_budget_still_fails_the_repository(db_session):
    agent, repo = _agent_repository(db_session, "diff-stuck")
    _agent_job(db_session, agent, repo)

    started = time.monotonic()
    with pytest.raises(HTTPException) as refused:
        await admit_repository_with_read_work_wait(
            db_session,
            repo,
            OPERATION_BACKUP,
            timeout_seconds=0.2,
            transient_only=False,
            poll_interval_seconds=0.01,
            retry_pause_seconds=0.0,
        )

    assert refused.value.status_code == 409
    assert refused.value.detail["params"]["active_operation"] == "repository.diff"
    assert time.monotonic() - started >= 0.2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_run_stops_waiting_and_queues_nothing(db_session):
    agent, repo = _agent_repository(db_session, "diff-cancelled")
    _agent_job(db_session, agent, repo)

    assert (
        await admit_repository_with_read_work_wait(
            db_session,
            repo,
            OPERATION_BACKUP,
            timeout_seconds=5,
            transient_only=False,
            poll_interval_seconds=0.01,
            is_cancelled=lambda: True,
        )
        == READ_WORK_CANCELLED
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_write_in_the_way_is_refused_without_waiting(db_session):
    # Another backup or a prune on the repository is not read work: the
    # plan gets the refusal at once, exactly as before.
    agent, repo = _agent_repository(db_session, "pruning")
    db_session.add(
        Operation(
            repository_id=repo.id,
            kind="prune",
            category="maintenance",
            status="running",
            trigger="manual",
            run_id="run-prune-running",
        )
    )
    db_session.commit()

    started = time.monotonic()
    with pytest.raises(HTTPException):
        await admit_repository_with_read_work_wait(
            db_session,
            repo,
            OPERATION_BACKUP,
            timeout_seconds=5,
            transient_only=False,
            poll_interval_seconds=0.01,
        )
    assert time.monotonic() - started < 1


# -- the cancel that lands while the backup is being prepared -----------------


def _plan_run_context(**overrides):
    from app.services.backup_plan_execution_service import PlanRunContext

    defaults = dict(
        plan_id=1,
        plan_name="nightly",
        source_type="local",
        source_ssh_connection_id=None,
        source_directories=["/data"],
        source_locations=[{"type": "local", "path": "/data"}],
        exclude_patterns=[],
        archive_name_template="{plan_name}-{now}",
        compression="lz4",
        custom_flags=None,
        upload_ratelimit_kib=None,
        upload_ratelimit_schedule_policies=[],
        repository_run_mode="series",
        max_parallel_repositories=1,
        failure_behavior="continue",
        pre_backup_script_id=None,
        post_backup_script_id=None,
        pre_backup_script_parameters={},
        post_backup_script_parameters={},
        script_hooks=[],
        run_repository_scripts=False,
        run_prune_after=False,
        run_compact_after=False,
        run_check_after=False,
        check_max_duration=3600,
        check_extra_flags=None,
        prune_keep_hourly=0,
        prune_keep_daily=7,
        prune_keep_weekly=4,
        prune_keep_monthly=6,
        prune_keep_quarterly=0,
        prune_keep_yearly=1,
        prune_keep_within=None,
        repository_count=1,
        timestamp="2026-09-20T00:00:00",
        date="2026-09-20",
        time_str="00-00-00",
        unix_timestamp="1789862400",
    )
    defaults.update(overrides)
    return PlanRunContext(**defaults)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancel_during_the_wait_is_not_overwritten_by_the_backup(db_engine):
    """`cancel_run` closes a repository row that has no backup operation
    yet, so it has nothing to cancel. The executor must not then claim that
    row and hand the runner a backup no one can stop."""
    from unittest.mock import patch

    from sqlalchemy.orm import sessionmaker

    import app.services.backup_plan_execution_service as plan_module
    from app.database.models import (
        BackupPlan,
        BackupPlanRun,
        BackupPlanRunRepository,
        Operation,
    )
    from app.services.backup_plan_execution_service import (
        CANCELLED_MESSAGE,
        RepositoryRunContext,
        backup_plan_execution_service,
    )

    testing_session_local = sessionmaker(bind=db_engine)
    session = testing_session_local()
    repo = Repository(
        name="cancel-race",
        path="/repos/cancel-race",
        encryption="none",
        repository_type="local",
    )
    plan = BackupPlan(name="nightly", source_directories='["/data"]')
    session.add_all([repo, plan])
    session.commit()
    run = BackupPlanRun(backup_plan_id=plan.id, trigger="manual", status="running")
    session.add(run)
    session.commit()
    child = BackupPlanRunRepository(
        backup_plan_run_id=run.id, repository_id=repo.id, status="pending"
    )
    session.add(child)
    session.commit()
    run_id, repo_id, child_id = run.id, repo.id, child.id
    session.close()

    real_create = plan_module.create_backup_operation

    def cancel_then_create(*args, **kwargs):
        """The cancel lands after admission, before the child is claimed."""
        closing = testing_session_local()
        try:
            closing.query(BackupPlanRun).filter(BackupPlanRun.id == run_id).update(
                {"status": "cancelled", "error_message": CANCELLED_MESSAGE}
            )
            closing.query(BackupPlanRunRepository).filter(
                BackupPlanRunRepository.id == child_id
            ).update({"status": "cancelled", "error_message": CANCELLED_MESSAGE})
            closing.commit()
        finally:
            closing.close()
        return real_create(*args, **kwargs)

    woke = []

    async def _never_reached(*args, **kwargs):
        # Without the conditional claim the executor gets this far; the
        # stub keeps the test from hanging on a backup nothing drives, so
        # the assertions below report the real failure.
        return "failed"

    with (
        patch.object(plan_module, "SessionLocal", testing_session_local),
        patch.object(plan_module, "create_backup_operation", cancel_then_create),
        patch.object(plan_module, "wake_runner", lambda: woke.append(True)),
        patch.object(plan_module, "wait_out_backup_operation", _never_reached),
    ):
        status = await backup_plan_execution_service._execute_repository(
            run_id,
            _plan_run_context(plan_id=1),
            RepositoryRunContext(
                repository_id=repo_id,
                repository_name="cancel-race",
                execution_order=0,
                compression="lz4",
                custom_flags=None,
                upload_ratelimit_kib=None,
                failure_behavior="continue",
            ),
        )

    assert status == "cancelled"
    check = testing_session_local()
    try:
        closed = check.query(BackupPlanRunRepository).get(child_id)
        assert closed.status == "cancelled"
        assert closed.backup_operation_id is None
        # the backup it was preparing never reached the runner
        assert (
            check.query(Operation)
            .filter(Operation.backup_plan_run_id == run_id)
            .count()
            == 0
        )
        assert woke == []
    finally:
        check.close()
