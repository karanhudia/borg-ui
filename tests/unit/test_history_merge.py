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
from app.services.operations.executors import index as index_exec


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    # The operations migration creates archives without AUTOINCREMENT,
    # although fresh model-created databases enable it. Exercise that schema.
    archive_options = Archive.__table__.dialect_options["sqlite"]
    original_autoincrement = archive_options["autoincrement"]
    try:
        archive_options["autoincrement"] = False
        Base.metadata.create_all(engine)
    finally:
        archive_options["autoincrement"] = original_autoincrement
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
        # a name the listing infers the same series from
        name=f"{series}-2026-09-{day:02d}T02:00:00",
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


def _listed(db, repo, removed):
    """The listing Borg would return: every archive of `repo` except the
    rows in `removed`."""
    gone = {a.id for a in removed}
    return [
        {"id": a.borg_id, "name": a.name, "start": f"{a.start:%Y-%m-%dT%H:%M:%S}"}
        for a in db.query(Archive).filter_by(repository_id=repo.id).all()
        if a.id not in gone
    ]


def _ctx(db, repo):
    return SimpleNamespace(
        db=db,
        repository_id=repo.id,
        operation_id=1,
        kind="archive_sync",
        params={},
        progress=AsyncMock(),
        log=lambda line: None,
        cancelled=lambda: False,
    )


async def _sync(db, repo, *removed, monkeypatch):
    """Run archive_sync on a listing that no longer has `removed`."""
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(True, _listed(db, repo, removed), "UTC")),
    )
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=0))
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    return await index_exec.run_archive_sync(_ctx(db, repo))


def _counts(out):
    return {k: out.result[k] for k in ("folded", "reset", "dropped")}


@pytest.mark.unit
async def test_removed_archive_folds_into_indexed_successor(db, repo, monkeypatch):
    r = _archive(db, repo, "r", 2, truncated=True)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "a", "added", after=3)
    _row(db, r, "b", "modified", before=1, after=2)
    _row(db, r, "c", "removed", before=4)
    _row(db, s, "a", "removed", before=3)
    _row(db, s, "b", "modified", before=2, after=9)
    _row(db, s, "c", "added", after=7)
    _row(db, s, "d", "added", after=1)
    r_id = r.id
    out = await _sync(db, repo, r, monkeypatch=monkeypatch)
    assert out.status == "completed"
    assert _counts(out) == {"folded": 1, "reset": 0, "dropped": 0}
    assert out.result["removed_archive_ids"] == [r_id]
    assert db.get(Archive, r_id) is None
    rows = {x.path: x for x in db.query(ArchiveChange).filter_by(archive_id=s.id)}
    assert set(rows) == {"b", "c", "d"}
    assert (rows["b"].size_before, rows["b"].size_after) == (1, 9)
    assert rows["c"].change == "modified"
    assert (rows["c"].size_before, rows["c"].size_after) == (4, 7)
    db.refresh(s)
    assert s.history_rows == 3 and s.history_truncated is True


@pytest.mark.unit
async def test_fold_sums_summary_counts(db, repo, monkeypatch):
    r = _archive(db, repo, "r", 2)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "x/y/z", "summary", count=10)
    _row(db, s, "x/y/z", "summary", count=5)
    await _sync(db, repo, r, monkeypatch=monkeypatch)
    row = db.query(ArchiveChange).filter_by(archive_id=s.id).one()
    assert row.change == "summary" and row.summary_count == 15


@pytest.mark.unit
async def test_unindexed_removed_archive_resets_indexed_successor(
    db, repo, monkeypatch
):
    r = _archive(db, repo, "r", 2, state="pending")
    s = _archive(db, repo, "s", 3)
    _row(db, s, "a", "added", after=1)
    r_id = r.id
    out = await _sync(db, repo, r, monkeypatch=monkeypatch)
    assert out.result["reset"] == 1
    db.refresh(s)
    assert s.history_state == "pending" and s.history_rows is None
    assert db.query(ArchiveChange).filter_by(archive_id=s.id).count() == 0
    assert db.get(Archive, r_id) is None


@pytest.mark.unit
async def test_reset_successor_of_an_agent_repository_is_skipped_not_pending(
    db, repo, monkeypatch
):
    """No history run comes for an agent's repository whose agent cannot
    produce the change listing, so a successor that loses its base takes the
    state the listing writes there; `pending` would read as "not yet" for
    good."""
    repo.executor_type = "agent"
    repo.execution_target = "agent"
    db.commit()
    r = _archive(db, repo, "r", 2, state="skipped")
    s = _archive(db, repo, "s", 3)
    _row(db, s, "a", "added", after=1)
    monkeypatch.setattr(index_exec, "archive_end_resolvable", lambda db, repo: True)
    out = await _sync(db, repo, r, monkeypatch=monkeypatch)
    assert out.result["reset"] == 1
    db.refresh(s)
    assert s.history_state == "skipped" and s.history_rows is None
    assert db.query(ArchiveChange).filter_by(archive_id=s.id).count() == 0


@pytest.mark.unit
async def test_reset_successor_of_a_capable_agent_repository_is_pending(
    db, repo, monkeypatch
):
    """An agent that produces the change listing gets its history run like
    any repository, so a successor that loses its base waits for it."""
    repo.executor_type = "agent"
    repo.execution_target = "agent"
    db.commit()
    r = _archive(db, repo, "r", 2, state="skipped")
    s = _archive(db, repo, "s", 3)
    _row(db, s, "a", "added", after=1)
    monkeypatch.setattr(index_exec, "archive_end_resolvable", lambda db, repo: True)
    monkeypatch.setattr(index_exec, "agent_supports_job", lambda *a, **k: True)
    out = await _sync(db, repo, r, monkeypatch=monkeypatch)
    assert out.result["reset"] == 1
    db.refresh(s)
    assert s.history_state == "pending" and s.history_rows is None


@pytest.mark.unit
async def test_pending_successor_or_no_successor_just_drops(db, repo, monkeypatch):
    r1 = _archive(db, repo, "r1", 1)
    _row(db, r1, "a", "added", after=1)
    s = _archive(db, repo, "s", 2, state="pending")
    r2 = _archive(db, repo, "newest", 5, series="other")
    ids = (r1.id, r2.id)
    out = await _sync(db, repo, r1, r2, monkeypatch=monkeypatch)
    assert _counts(out) == {"folded": 0, "reset": 0, "dropped": 2}
    assert all(db.get(Archive, i) is None for i in ids)
    assert db.query(ArchiveChange).count() == 0
    db.refresh(s)
    assert s.history_state == "pending"


@pytest.mark.unit
async def test_successor_is_found_within_the_same_series_only(db, repo, monkeypatch):
    r = _archive(db, repo, "r", 2)
    other = _archive(db, repo, "o", 3, series="other")
    _row(db, r, "a", "added", after=1)
    _row(db, other, "b", "added", after=1)
    out = await _sync(db, repo, r, monkeypatch=monkeypatch)
    assert out.result["dropped"] == 1
    assert {x.path for x in db.query(ArchiveChange).filter_by(archive_id=other.id)} == {
        "b"
    }


@pytest.mark.unit
async def test_other_repositories_are_untouched(db, repo, monkeypatch):
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add(other)
    db.commit()
    foreign = _archive(db, other, "foreign", 2)
    r = _archive(db, repo, "r", 2)
    out = await _sync(db, repo, r, monkeypatch=monkeypatch)
    assert out.result["dropped"] == 1
    assert db.get(Archive, foreign.id) is not None


@pytest.mark.unit
async def test_merge_is_atomic_per_archive(db, repo):
    r = _archive(db, repo, "r", 2)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "a", "added", after=3)
    _row(db, s, "b", "added", after=1)
    with patch.object(
        db, "bulk_insert_mappings", side_effect=RuntimeError("disk full")
    ):
        with pytest.raises(RuntimeError):
            history.merge_removed_archive(db, r)
    assert db.get(Archive, r.id) is not None
    assert {x.path for x in db.query(ArchiveChange).filter_by(archive_id=s.id)} == {"b"}


@pytest.mark.unit
async def test_fold_result_is_capped_like_an_indexed_archive(db, repo, monkeypatch):
    """fold_pair keeps rows that are distinct in either archive, so a successor
    could pass index_history_max_rows after one merge and grow further with
    each later removal. The cap and its summary rollup apply to the fold too."""
    monkeypatch.setattr(history.settings, "index_history_max_rows", 3)
    r = _archive(db, repo, "r", 2)
    s = _archive(db, repo, "s", 3)
    for i in range(3):
        _row(db, r, f"old/dir/f{i}", "added", after=1)
    for i in range(3):
        _row(db, s, f"new/dir/f{i}", "added", after=1)

    out = await _sync(db, repo, r, monkeypatch=monkeypatch)

    assert out.result["folded"] == 1
    rows = db.query(ArchiveChange).filter_by(archive_id=s.id).all()
    detail = [x for x in rows if x.change != "summary"]
    summary = [x for x in rows if x.change == "summary"]
    assert len(detail) == 3
    assert sum(x.summary_count for x in summary) == 3
    db.refresh(s)
    assert s.history_rows == len(rows) and s.history_truncated is True


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["full", "archives"])
async def test_a_removed_archive_is_deleted_by_the_listing_in_every_mode(
    db, repo, monkeypatch, mode
):
    """#1141: the `archives` index mode runs no history stage, and the row of
    a removed archive stayed in the table for good. The listing that finds
    the removal deletes it, whatever the mode."""
    repo.index_mode = mode
    db.commit()
    keep = _archive(db, repo, "keep", 3, state="pending")
    gone = _archive(db, repo, "gone", 2, state="pending")
    gone_id = gone.id
    await _sync(db, repo, gone, monkeypatch=monkeypatch)
    assert db.get(Archive, gone_id) is None
    db.refresh(repo)
    assert repo.archive_count == 1
    assert [a.id for a in db.query(Archive).all()] == [keep.id]


@pytest.mark.unit
async def test_rows_left_by_an_earlier_listing_are_deleted_by_the_next(
    db, repo, monkeypatch
):
    """Rows the old behaviour left behind (every `archives` repository, or a
    listing that died before its merge) are simply absent from the next
    listing, which deletes them."""
    keep = _archive(db, repo, "keep", 5, state="pending")
    lingering = [_archive(db, repo, f"old{d}", d, state="pending") for d in (1, 2)]
    ids = [a.id for a in lingering]
    # an earlier listing already reported them removed and left them in place
    db.add(
        Operation(
            repository_id=repo.id,
            kind="archive_sync",
            category="index",
            status="completed",
            trigger="reconcile",
            priority=20,
            run_id="old",
            completed_at=datetime(2026, 9, 6),
            result={"removed_archive_ids": ids},
        )
    )
    db.commit()
    out = await _sync(db, repo, *lingering, monkeypatch=monkeypatch)
    assert sorted(out.result["removed_archive_ids"]) == sorted(ids)
    assert [a.id for a in db.query(Archive).all()] == [keep.id]


@pytest.mark.unit
async def test_a_history_merge_queued_before_the_upgrade_is_skipped(db, repo):
    """history_merge left the chains; a row queued by an older version
    finishes `skipped`, which frees its dependents, and the next listing
    deletes whatever it would have."""
    op = Operation(
        repository_id=repo.id,
        kind="history_merge",
        category="index",
        status="running",
        trigger="followup",
        priority=10,
        run_id="old",
    )
    db.add(op)
    db.commit()
    out = await history.run_history_merge(
        SimpleNamespace(db=db, repository_id=repo.id, operation=op)
    )
    assert out.status == "skipped"
    assert out.skip_reason == "merged_by_archive_sync"
