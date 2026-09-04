from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Archive,
    ArchiveChange,
    Base,
    Operation,
    Repository,
    SystemSettings,
)
from app.services.operations.executors import history


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


def _archive(db, repo, name, day, state="indexed", series="nas", truncated=False):
    a = Archive(
        repository_id=repo.id,
        borg_id=f"id-{name}",
        name=name,
        series=series,
        start=datetime(2026, 9, day, 2),
        history_state=state,
        history_truncated=truncated,
    )
    db.add(a)
    db.commit()
    return a


def _row(db, archive, path, change, before=None, after=None, count=None):
    db.add(
        ArchiveChange(
            archive_id=archive.id,
            path=path,
            change=change,
            size_before=before,
            size_after=after,
            summary_count=count,
        )
    )
    db.commit()


def _ops(db, repo, removed_ids):
    parent = Operation(
        repository_id=repo.id,
        kind="archive_sync",
        category="index",
        status="completed",
        trigger="reconcile",
        priority=20,
        run_id="run",
        result={"removed_archive_ids": removed_ids},
    )
    db.add(parent)
    db.commit()
    child = Operation(
        repository_id=repo.id,
        kind="history_merge",
        category="index",
        status="running",
        trigger="reconcile",
        priority=20,
        run_id="run",
        depends_on_id=parent.id,
    )
    db.add(child)
    db.commit()
    return child


def _ctx(db, repo, op):
    return SimpleNamespace(
        db=db,
        repository_id=repo.id,
        operation_id=op.id,
        kind="history_merge",
        params={},
        operation=op,
        progress=AsyncMock(),
        log=lambda line: None,
        cancelled=lambda: False,
    )


@pytest.mark.unit
async def test_removed_archive_folds_into_indexed_successor(db, repo):
    r = _archive(db, repo, "r", 2, truncated=True)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "a", "added", after=3)
    _row(db, r, "b", "modified", before=1, after=2)
    _row(db, r, "c", "removed", before=4)
    _row(db, s, "a", "removed", before=3)
    _row(db, s, "b", "modified", before=2, after=9)
    _row(db, s, "c", "added", after=7)
    _row(db, s, "d", "added", after=1)
    op = _ops(db, repo, [r.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.status == "completed"
    assert out.result == {"merged": 1, "folded": 1, "reset": 0, "dropped": 0}
    assert db.get(Archive, r.id) is None
    rows = {x.path: x for x in db.query(ArchiveChange).filter_by(archive_id=s.id)}
    assert set(rows) == {"b", "c", "d"}
    assert (rows["b"].size_before, rows["b"].size_after) == (1, 9)
    assert rows["c"].change == "modified"
    assert (rows["c"].size_before, rows["c"].size_after) == (4, 7)
    db.refresh(s)
    assert s.history_rows == 3 and s.history_truncated is True


@pytest.mark.unit
async def test_fold_sums_summary_counts(db, repo):
    r = _archive(db, repo, "r", 2)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "x/y/z", "summary", count=10)
    _row(db, s, "x/y/z", "summary", count=5)
    op = _ops(db, repo, [r.id])
    await history.run_history_merge(_ctx(db, repo, op))
    row = db.query(ArchiveChange).filter_by(archive_id=s.id).one()
    assert row.change == "summary" and row.summary_count == 15


@pytest.mark.unit
async def test_unindexed_removed_archive_resets_indexed_successor(db, repo):
    r = _archive(db, repo, "r", 2, state="pending")
    s = _archive(db, repo, "s", 3)
    _row(db, s, "a", "added", after=1)
    op = _ops(db, repo, [r.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["reset"] == 1
    db.refresh(s)
    assert s.history_state == "pending" and s.history_rows is None
    assert db.query(ArchiveChange).filter_by(archive_id=s.id).count() == 0
    assert db.get(Archive, r.id) is None


@pytest.mark.unit
async def test_pending_successor_or_no_successor_just_drops(db, repo):
    r1 = _archive(db, repo, "r1", 1)
    _row(db, r1, "a", "added", after=1)
    s = _archive(db, repo, "s", 2, state="pending")
    r2 = _archive(db, repo, "newest", 5, series="other")
    op = _ops(db, repo, [r1.id, r2.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["dropped"] == 2 and out.result["merged"] == 2
    assert db.get(Archive, r1.id) is None and db.get(Archive, r2.id) is None
    assert db.query(ArchiveChange).count() == 0
    db.refresh(s)
    assert s.history_state == "pending"


@pytest.mark.unit
async def test_successor_is_found_within_the_same_series_only(db, repo):
    r = _archive(db, repo, "r", 2)
    other = _archive(db, repo, "o", 3, series="other")
    _row(db, r, "a", "added", after=1)
    _row(db, other, "b", "added", after=1)
    op = _ops(db, repo, [r.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["dropped"] == 1
    assert {x.path for x in db.query(ArchiveChange).filter_by(archive_id=other.id)} == {
        "b"
    }


@pytest.mark.unit
async def test_ignores_other_repositories_and_missing_ids(db, repo):
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add(other)
    db.commit()
    foreign = Archive(
        repository_id=other.id,
        borg_id="f",
        name="f",
        series="d",
        start=datetime(2026, 9, 1),
    )
    db.add(foreign)
    db.commit()
    op = _ops(db, repo, [foreign.id, 9999])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["merged"] == 0
    assert db.get(Archive, foreign.id) is not None


@pytest.mark.unit
async def test_no_dependency_result_merges_nothing(db, repo):
    op = Operation(
        repository_id=repo.id,
        kind="history_merge",
        category="index",
        status="running",
        trigger="manual",
        priority=0,
        run_id="x",
    )
    db.add(op)
    db.commit()
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["merged"] == 0


@pytest.mark.unit
async def test_dependency_that_is_not_archive_sync_merges_nothing(db, repo):
    parent = Operation(
        repository_id=repo.id,
        kind="stats",
        category="index",
        status="completed",
        trigger="manual",
        priority=0,
        run_id="x",
        result={"removed_archive_ids": [1]},
    )
    db.add(parent)
    db.commit()
    child = Operation(
        repository_id=repo.id,
        kind="history_merge",
        category="index",
        status="running",
        trigger="manual",
        priority=0,
        run_id="x",
        depends_on_id=parent.id,
    )
    db.add(child)
    db.commit()
    assert history.removed_archive_ids_from_dependency(db, child) == []


@pytest.mark.unit
async def test_merge_is_atomic_per_archive(db, repo):
    r = _archive(db, repo, "r", 2)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "a", "added", after=3)
    _row(db, s, "b", "added", after=1)
    _ops(db, repo, [r.id])
    with patch.object(
        db, "bulk_insert_mappings", side_effect=RuntimeError("disk full")
    ):
        with pytest.raises(RuntimeError):
            history.merge_removed_archive(db, r)
    assert db.get(Archive, r.id) is not None
    assert {x.path for x in db.query(ArchiveChange).filter_by(archive_id=s.id)} == {"b"}


@pytest.mark.unit
async def test_progress_and_log_name_the_removed_archive(db, repo):
    r = _archive(db, repo, "gone", 2)
    _ops(db, repo, [r.id])
    op = _ops(db, repo, [r.id])
    ctx = _ctx(db, repo, op)
    logged = []
    ctx.log = logged.append
    await history.run_history_merge(ctx)
    assert logged == ["gone: dropped"]
    assert ctx.progress.await_args_list[-1].kwargs["message"] == "gone"
