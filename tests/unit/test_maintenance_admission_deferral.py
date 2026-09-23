"""An admission refusal of a runner-driven agent maintenance operation is
deferred by the runner, not recorded as a failure (#1155)."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import (
    Archive,
    Base,
    Operation,
    Repository,
    SystemSettings,
)
from app.services.operations import executors
from app.services.operations.enqueue import enqueue
from app.services.operations.runner import OperationRunner


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def repo(db):
    r = Repository(
        name="r",
        path="/tmp/r",
        encryption="none",
        compression="lz4",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
    )
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


@pytest.fixture()
def runner(session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    executors.load_default_executors()
    return OperationRunner(
        session_factory=session_factory,
        registry=executors.REGISTRY,
        poll_interval=0.01,
        deferral_delay=0.0,
    )


def _refusal() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "key": "backend.errors.jobs.repositoryOperationActive",
            "params": {
                "active_operation": "list_archives",
                "active_job_table": "agent_jobs",
                "active_status": "running",
            },
        },
    )


async def _run_once(runner):
    await runner.tick()
    await asyncio.gather(*list(runner.running_tasks.values()), return_exceptions=True)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind, params",
    [
        ("prune", {}),
        ("compact", {}),
        ("check", {}),
        ("delete_archive", {"archive_name": "a1"}),
    ],
)
async def test_a_refused_agent_maintenance_operation_is_deferred(
    db, repo, runner, session_factory, kind, params
):
    """The listing of a backup's `stats` follow-up holds the repository for a
    few seconds; the maintenance operation the runner starts beside it is
    refused by admission. The runner defers it like any other refused kind:
    the row goes back to `queued` with a deferral count, and nothing records
    it as a failure."""
    op = enqueue(db, kind, repository_id=repo.id, trigger="followup", params=params)

    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_refusal(),
        ),
    ):
        await _run_once(runner)

    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "queued"
    assert row.params["deferrals"] == 1
    assert row.error_message is None
    assert row.started_at is None
    assert row.completed_at is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_refused_retention_comparison_is_deferred_and_fails_no_dry_run(
    db, repo, runner, session_factory, monkeypatch
):
    """The measured case: a comparison's four dry runs are refused by the
    listing of the same backup's `stats` follow-up. The comparison is
    deferred as a whole, and none of its dry runs is left as a failure."""
    from app.services import prune_compare as pc

    for i in range(3):
        db.add(
            Archive(
                repository_id=repo.id,
                name=f"a{i}",
                series=f"a{i}",
                borg_id=f"{i:064x}",
                start=datetime(2026, 9, 1) + timedelta(days=i),
                first_seen_at=datetime(2026, 9, 1),
                last_seen_at=datetime(2026, 9, 1),
            )
        )
    db.commit()
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "plan",
            "plan_name": "p",
            "keep_hourly": 0,
            "keep_daily": 1,
            "keep_weekly": 0,
            "keep_monthly": 0,
            "keep_quarterly": 0,
            "keep_yearly": 0,
            "keep_within": None,
        },
    )
    op = enqueue(db, "prune_compare", repository_id=repo.id, trigger="followup")

    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_refusal(),
        ),
    ):
        await _run_once(runner)

    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "queued"
    assert row.params["deferrals"] == 1
    assert row.error_message is None
    dry_runs = db.query(Operation).filter(Operation.depends_on_id == op.id).all()
    # The first refusal ends the comparison: the other candidates would only
    # be refused the same way.
    assert len(dry_runs) == 1
    assert dry_runs[0].status == "skipped"
    assert dry_runs[0].skip_reason == "repository_busy"
    assert dry_runs[0].completed_at is not None
    assert dry_runs[0].error_message == ("list_archives is active on the repository")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_deferred_comparison_is_held_while_its_stage_is_paused(
    db, repo, runner, session_factory, monkeypatch
):
    """A deferred comparison is an ordinary queued row: once its deferral
    runs out while the retention stage is paused, the runner holds it like
    any other queued follow-up of that stage, without failing it or
    spending another deferral."""
    import time

    from app.services import prune_compare as pc

    for i in range(3):
        db.add(
            Archive(
                repository_id=repo.id,
                name=f"a{i}",
                series=f"a{i}",
                borg_id=f"{i:064x}",
                start=datetime(2026, 9, 1) + timedelta(days=i),
                first_seen_at=datetime(2026, 9, 1),
                last_seen_at=datetime(2026, 9, 1),
            )
        )
    db.commit()
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "plan",
            "plan_name": "p",
            "keep_hourly": 0,
            "keep_daily": 1,
            "keep_weekly": 0,
            "keep_monthly": 0,
            "keep_quarterly": 0,
            "keep_yearly": 0,
            "keep_within": None,
        },
    )
    op = enqueue(db, "prune_compare", repository_id=repo.id, trigger="followup")

    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_refusal(),
        ) as queue,
    ):
        await _run_once(runner)
        db.expire_all()
        assert db.get(Operation, op.id).params["deferrals"] == 1
        attempts = queue.call_count

        db.query(SystemSettings).one().paused_stages = ["retention"]
        row = db.get(Operation, op.id)
        row.params = {**row.params, "deferred_until": time.time() - 1}
        db.commit()
        await _run_once(runner)

    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "queued"
    assert row.params["deferrals"] == 1
    assert row.error_message is None
    assert queue.call_count == attempts


def _agent_maintenance_row(db, repo, kind="prune"):
    from app.services.operations.maintenance_start import start_inline_maintenance

    return start_inline_maintenance(db, repo, kind, params={}, user_id=None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_raise_busy_keeps_the_refusal_and_leaves_the_row_to_the_caller(
    db, repo, session_factory
):
    from app.core.borg_router import BorgRouter

    row = _agent_maintenance_row(db, repo)
    refusal = _refusal()
    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=refusal,
        ),
        pytest.raises(HTTPException) as raised,
    ):
        await BorgRouter(repo)._run_agent_maintenance(
            job_kind="repository.prune",
            maintenance_kind="prune",
            maintenance_job_id=row.id,
            raise_busy=True,
        )

    assert raised.value is refusal
    db.expire_all()
    stored = db.get(Operation, row.id)
    assert stored.status == "running"
    assert stored.error_message is None and stored.completed_at is None


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, raised_type",
    [
        # admission refuses for a reason the runner does not defer
        (
            HTTPException(
                status_code=409,
                detail={"key": "backend.errors.agents.noQueueableAgent"},
            ),
            RuntimeError,
        ),
        (RuntimeError("database is locked"), RuntimeError),
    ],
)
async def test_raise_busy_still_fails_the_row_for_any_other_error(
    db, repo, session_factory, error, raised_type
):
    """The orphan guard stays for everything but the refusal the runner
    defers: such a row would otherwise block the repository for good."""
    from app.core.borg_router import BorgRouter

    row = _agent_maintenance_row(db, repo)
    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=error,
        ),
        pytest.raises(raised_type),
    ):
        await BorgRouter(repo)._run_agent_maintenance(
            job_kind="repository.prune",
            maintenance_kind="prune",
            maintenance_job_id=row.id,
            raise_busy=True,
        )

    db.expire_all()
    stored = db.get(Operation, row.id)
    assert stored.status == "failed"
    assert stored.error_message.startswith("agent job could not be queued: ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_dry_run_without_raise_busy_still_fails_its_row(
    db, repo, session_factory
):
    """The preview page's own dry run answers the user at once: its refusal
    is a failure, as before."""
    from app.services.prune_preview import Retention, run_prune_dry_run

    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_refusal(),
        ),
        pytest.raises(RuntimeError),
    ):
        await run_prune_dry_run(db, repo, Retention(keep_daily=1), user_id=None)

    db.expire_all()
    row = db.query(Operation).filter(Operation.kind == "prune").one()
    assert row.status == "failed"
    assert row.skip_reason is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_refused_comparison_keeps_the_stored_rows(db, repo, monkeypatch):
    """A refusal after some candidates completed ends the comparison before
    anything is replaced: the rows of the last full comparison stay."""
    from unittest.mock import AsyncMock

    from app.database.models import PruneComparison
    from app.services import prune_compare as pc
    from app.services.prune_preview import CandidateResult

    for i in range(2):
        db.add(
            Archive(
                repository_id=repo.id,
                name=f"a{i}",
                series=f"a{i}",
                borg_id=f"{i:064x}",
                start=datetime(2026, 9, 1) + timedelta(days=i),
                first_seen_at=datetime(2026, 9, 1),
                last_seen_at=datetime(2026, 9, 1),
            )
        )
    db.add(
        PruneComparison(
            repository_id=repo.id,
            candidate="standard",
            label="Standard",
            kept_count=1,
            deleted_count=1,
            freed_at_least=5,
            archive_count_at=2,
            computed_at=datetime(2026, 1, 1),
        )
    )
    db.commit()
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "plan",
            "plan_name": "p",
            "keep_hourly": 0,
            "keep_daily": 1,
            "keep_weekly": 0,
            "keep_monthly": 0,
            "keep_quarterly": 0,
            "keep_yearly": 0,
            "keep_within": None,
        },
    )
    done = CandidateResult(
        operation=type("Op", (), {"id": None})(),
        log="",
        joined=[],
        candidates=[],
        partial_measure=False,
        freed_at_least=0,
        kept_count=2,
        deleted_count=0,
    )
    fake = AsyncMock(side_effect=[done, _refusal()])
    with patch.object(pc, "run_candidate", new=fake), pytest.raises(HTTPException):
        await pc.run_comparison(db, repo, run_id="run", depends_on_id=None)

    assert fake.await_args.kwargs["raise_busy"] is True
    rows = db.query(PruneComparison).filter_by(repository_id=repo.id).all()
    assert [r.candidate for r in rows] == ["standard"]


@pytest.fixture()
def agent_repo(db):
    """An agent repository the real queue function accepts."""
    from app.database.models import AgentMachine

    agent = AgentMachine(
        name="agent",
        agent_id="agt_agent",
        token_hash="x",
        token_prefix="x",
        status="online",
        capabilities=["repository.prune", "repository.compact"],
    )
    db.add(agent)
    db.flush()
    r = Repository(
        name="agent-repo",
        path="/repos/agent",
        encryption="none",
        compression="lz4",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=agent.id,
    )
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


def _agent_reports_success(session_factory):
    """Stands in for the agent: the job completes and its report closes the
    linked operation, as `_finish_linked_repository_operation_job` does."""
    from app.database.models import AgentJob, utc_now

    async def wait(db, job_id, timeout_seconds=None):
        s = session_factory()
        try:
            job = s.get(AgentJob, job_id)
            job.status = "completed"
            linked = job.payload["operation"]["maintenance_job"]["id"]
            op = s.get(Operation, linked)
            op.status = "completed"
            op.started_at = op.started_at or utc_now()
            op.completed_at = utc_now()
            s.commit()
        finally:
            s.close()
        return {"return_code": 0}

    return wait


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_deferred_prune_does_not_refuse_the_compact_that_took_the_lane(
    db, agent_repo, runner, session_factory
):
    """The sequence the deferral opens: a prune is deferred after a refusal
    and waits in the queue; a compact of the same repository takes the free
    lane meanwhile. The deferred prune holds no lock and starts only once
    the compact has left the lane, so it does not refuse the compact's
    agent job; then the prune runs too. Real queue function and admission,
    only the agent is simulated."""
    import time

    from app.database.models import AgentJob

    prune = enqueue(db, "prune", repository_id=agent_repo.id, trigger="followup")
    prune.params = {"deferrals": 1, "deferred_until": time.time() + 300}
    compact = enqueue(db, "compact", repository_id=agent_repo.id, trigger="followup")
    db.commit()

    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
        patch(
            "app.services.repository_executor.wait_for_agent_repository_operation_job",
            side_effect=_agent_reports_success(session_factory),
        ),
    ):
        await _run_once(runner)
        db.expire_all()
        assert db.get(Operation, compact.id).status == "completed"
        assert db.get(Operation, prune.id).status == "queued"

        # the prune's deferral runs out
        row = db.get(Operation, prune.id)
        row.params = {**row.params, "deferred_until": time.time() - 1}
        db.commit()
        await _run_once(runner)

    db.expire_all()
    assert db.get(Operation, prune.id).status == "completed"
    kinds = sorted(j.payload["job_kind"] for j in db.query(AgentJob).all())
    assert kinds == ["repository.compact", "repository.prune"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_without_raise_busy_a_queued_operation_still_refuses(
    db, agent_repo, session_factory
):
    """Every other caller keeps the admission as it was."""
    from app.core.borg_router import BorgRouter

    enqueue(db, "prune", repository_id=agent_repo.id, trigger="followup")
    compact = enqueue(db, "compact", repository_id=agent_repo.id, trigger="followup")
    compact.status = "running"
    db.commit()

    with (
        patch("app.database.database.SessionLocal", side_effect=session_factory),
        pytest.raises(RuntimeError, match="prune is active on the repository"),
    ):
        await BorgRouter(agent_repo).compact(compact.id)


@pytest.mark.unit
def test_ignore_queued_operations_keeps_running_operations_and_agent_jobs(db, repo):
    from app.database.models import AgentJob, AgentMachine
    from app.services.job_admission import list_active_repository_work

    queued = enqueue(db, "prune", repository_id=repo.id, trigger="followup")
    running = enqueue(db, "check", repository_id=repo.id, trigger="followup")
    running.status = "running"
    agent = AgentMachine(name="a", agent_id="a", token_hash="x", token_prefix="x")
    db.add(agent)
    db.commit()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="queued",
        payload={
            "job_kind": "repository.list_archives",
            "repository": {"id": repo.id, "path": repo.path},
        },
    )
    db.add(job)
    db.commit()

    def seen(**kwargs):
        return {
            (w.job_table, w.job_id)
            for w in list_active_repository_work(db, repo, **kwargs)
        }

    assert seen() == {
        ("operations", queued.id),
        ("operations", running.id),
        ("agent_jobs", job.id),
    }
    assert seen(ignore_queued_operations=True) == {
        ("operations", running.id),
        ("agent_jobs", job.id),
    }


def _lane_row(db, repo, kind, status):
    row = enqueue(db, kind, repository_id=repo.id, trigger="followup")
    row.status = status
    db.commit()
    return row


@pytest.mark.unit
@pytest.mark.parametrize(
    "case",
    ["no row", "queued", "not exclusive", "other repository"],
)
def test_ignore_queued_operations_is_refused_outside_the_repository_lane(
    db, agent_repo, case
):
    """Leaving queued operations out of admission is only sound while the
    caller's own row holds the repository lane. Any other caller is a
    programming error and fails loudly rather than letting admission stop
    counting a queued prune."""
    from app.database.models import AgentJob
    from app.services.repository_executor import queue_agent_repository_operation_job

    if case == "no row":
        maintenance_job_id = None
    elif case == "queued":
        maintenance_job_id = _lane_row(db, agent_repo, "prune", "queued").id
    elif case == "not exclusive":
        maintenance_job_id = _lane_row(db, agent_repo, "restore_check", "running").id
    else:
        other = Repository(
            name="other", path="/repos/other", encryption="none", compression="lz4"
        )
        db.add(other)
        db.commit()
        maintenance_job_id = _lane_row(db, other, "prune", "running").id

    with pytest.raises(RuntimeError, match="repository lane"):
        queue_agent_repository_operation_job(
            db,
            agent_repo,
            job_kind="repository.prune",
            maintenance_job_kind="prune",
            maintenance_job_id=maintenance_job_id,
            ignore_queued_operations=True,
        )
    assert db.query(AgentJob).count() == 0


@pytest.mark.unit
def test_ignore_queued_operations_is_accepted_from_the_repository_lane(db, agent_repo):
    from app.services.repository_executor import queue_agent_repository_operation_job

    enqueue(db, "compact", repository_id=agent_repo.id, trigger="followup")
    row = _lane_row(db, agent_repo, "prune", "running")

    job = queue_agent_repository_operation_job(
        db,
        agent_repo,
        job_kind="repository.prune",
        maintenance_job_kind="prune",
        maintenance_job_id=row.id,
        ignore_queued_operations=True,
    )
    assert job.payload["job_kind"] == "repository.prune"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_plain_failure_leaves_skip_reason_alone(db, repo):
    from app.services.operations.maintenance_start import fail_inline_maintenance

    row = _agent_maintenance_row(db, repo)
    row.skip_reason = "left by someone else"
    db.commit()

    assert await fail_inline_maintenance(db, row, RuntimeError("rc 2"))
    db.expire_all()
    stored = db.get(Operation, row.id)
    assert stored.status == "failed"
    assert stored.skip_reason == "left by someone else"
