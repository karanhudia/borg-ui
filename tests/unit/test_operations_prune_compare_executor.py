from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, Base, Operation, Repository, SystemSettings
from app.services.operations.executors import prune_compare as executor


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
def repo(db):
    r = Repository(
        name="r", path="/tmp/r", encryption="none", compression="lz4", borg_version=1
    )
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


def _op(db, repo):
    op = Operation(
        repository_id=repo.id,
        kind="prune_compare",
        category="maintenance",
        status="running",
        trigger="followup",
        priority=10,
        run_id="run-1",
    )
    db.add(op)
    db.commit()
    return op


def _ctx(db, repo, op):
    return SimpleNamespace(
        db=db,
        repository_id=repo.id,
        operation_id=op.id,
        operation=op,
        kind="prune_compare",
        params={},
        progress=AsyncMock(),
        log=lambda line: None,
        cancelled=lambda: False,
    )


def _archives(db, repo, n):
    for i in range(n):
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_an_observe_only_repository(db, repo):
    repo.mode = "observe"
    db.commit()
    out = await executor.run_prune_compare(_ctx(db, repo, _op(db, repo)))
    assert (out.status, out.skip_reason) == ("skipped", "observe_only")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_with_fewer_than_two_archives(db, repo):
    _archives(db, repo, 1)
    out = await executor.run_prune_compare(_ctx(db, repo, _op(db, repo)))
    assert (out.status, out.skip_reason) == ("skipped", "too_few_archives")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_while_write_maintenance_is_pending(db, repo):
    _archives(db, repo, 3)
    db.add(
        Operation(
            repository_id=repo.id,
            kind="prune",
            category="maintenance",
            status="queued",
            trigger="manual",
            priority=0,
            run_id="x",
        )
    )
    db.commit()
    out = await executor.run_prune_compare(_ctx(db, repo, _op(db, repo)))
    assert (out.status, out.skip_reason) == ("skipped", "maintenance_pending")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runs_the_comparison_under_its_own_run(db, repo):
    _archives(db, repo, 3)
    op = _op(db, repo)
    fake = AsyncMock(return_value=[SimpleNamespace(candidate="standard")] * 2)
    with patch.object(executor, "run_comparison", new=fake):
        out = await executor.run_prune_compare(_ctx(db, repo, op))
    assert out.status == "completed"
    assert out.result == {"candidates": 2}
    assert fake.call_args.kwargs == {"run_id": "run-1", "depends_on_id": op.id}


@pytest.mark.unit
def test_executor_is_registered():
    from app.services.operations.executors import get_executor, load_default_executors

    load_default_executors()
    assert get_executor("prune_compare") is executor.run_prune_compare
