from datetime import datetime, timedelta
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
        result={
            "removed_archive_ids": removed_ids,
            "removed_archive_generations": {
                str(a.id): a.generation_id
                for a in db.query(Archive).filter(Archive.id.in_(removed_ids)).all()
            },
            "removed_archive_last_seen_at": {
                str(a.id): a.last_seen_at.isoformat()
                for a in db.query(Archive).filter(Archive.id.in_(removed_ids)).all()
            },
            "removed_archive_borg_ids": {
                str(a.id): a.borg_id
                for a in db.query(Archive).filter(Archive.id.in_(removed_ids)).all()
            },
        },
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
async def test_reset_successor_of_an_agent_repository_is_skipped_not_pending(db, repo):
    """No history run comes for an agent's repository on any plan, so a
    successor that loses its base takes the state the listing writes there;
    `pending` would read as "not yet" for good."""
    repo.executor_type = "agent"
    repo.execution_target = "agent"
    db.commit()
    r = _archive(db, repo, "r", 2, state="skipped")
    s = _archive(db, repo, "s", 3)
    _row(db, s, "a", "added", after=1)
    op = _ops(db, repo, [r.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["reset"] == 1
    db.refresh(s)
    assert s.history_state == "skipped" and s.history_rows is None
    assert db.query(ArchiveChange).filter_by(archive_id=s.id).count() == 0


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
    assert history.removed_archive_targets_from_dependency(db, child) == []


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
    op = _ops(db, repo, [r.id])

    out = await history.run_history_merge(_ctx(db, repo, op))

    assert out.result["folded"] == 1
    rows = db.query(ArchiveChange).filter_by(archive_id=s.id).all()
    detail = [x for x in rows if x.change != "summary"]
    summary = [x for x in rows if x.change == "summary"]
    assert len(detail) == 3
    assert sum(x.summary_count for x in summary) == 3
    db.refresh(s)
    assert s.history_rows == len(rows) and s.history_truncated is True


@pytest.mark.unit
@pytest.mark.parametrize("interrupt_after_delete", [False, True])
async def test_replay_preserves_new_archive_reusing_deleted_id(
    db, repo, interrupt_after_delete
):
    removed = _archive(db, repo, "removed", 1)
    removed_id = removed.id
    op = _ops(db, repo, [removed_id])
    operation_id = op.id
    repository_id = repo.id
    ctx = _ctx(db, repo, op)
    if interrupt_after_delete:
        ctx.progress.side_effect = RuntimeError("progress unavailable")
        with pytest.raises(RuntimeError, match="progress unavailable"):
            await history.run_history_merge(ctx)
    else:
        await history.run_history_merge(ctx)
    # The runner's terminal write did not commit. Only executor checkpoints
    # survive a new session, as when an abandoned operation is requeued.
    db.rollback()
    db.expunge_all()
    op = db.get(Operation, operation_id)
    repo = db.get(Repository, repository_id)
    replacement = _archive(db, repo, "replacement", 2)
    assert replacement.id == removed_id
    _row(db, replacement, "keep", "added", after=9)

    out = await history.run_history_merge(_ctx(db, repo, op))

    assert db.get(Archive, removed_id) is not None
    assert db.query(ArchiveChange).filter_by(archive_id=removed_id).one().path == "keep"
    assert out.result == {"merged": 1, "folded": 0, "reset": 0, "dropped": 1}


@pytest.mark.unit
@pytest.mark.parametrize("foreign_target", [False, True])
async def test_replay_does_not_revisit_previously_skipped_ids(db, repo, foreign_target):
    if foreign_target:
        other = Repository(name="other", path="/tmp/other", encryption="none")
        db.add(other)
        db.commit()
        target = _archive(db, other, "foreign", 1)
        target_id = target.id
    else:
        target_id = 1
    op = _ops(db, repo, [target_id])
    await history.run_history_merge(_ctx(db, repo, op))
    if foreign_target:
        db.delete(target)
        db.commit()
    replacement = _archive(db, repo, "replacement", 2)
    assert replacement.id == target_id

    out = await history.run_history_merge(_ctx(db, repo, op))

    assert db.get(Archive, target_id) is not None
    assert out.result["merged"] == 0


@pytest.mark.unit
async def test_failed_merge_commit_does_not_checkpoint_uncommitted_deletion(db, repo):
    removed = _archive(db, repo, "removed", 1)
    removed_id = removed.id
    op = _ops(db, repo, [removed_id])
    with patch.object(db, "commit", side_effect=RuntimeError("disk full")):
        with pytest.raises(RuntimeError, match="disk full"):
            await history.run_history_merge(_ctx(db, repo, op))
    assert db.get(Archive, removed_id) is not None

    out = await history.run_history_merge(_ctx(db, repo, op))

    assert db.get(Archive, removed_id) is None
    assert out.result == {"merged": 1, "folded": 0, "reset": 0, "dropped": 1}


@pytest.mark.unit
@pytest.mark.parametrize("partially_merged", [False, True])
async def test_overtaking_chain_cannot_make_merge_delete_reused_unvisited_id(
    db, repo, partially_merged
):
    first = _archive(db, repo, "first", 1, series="first")
    second = _archive(db, repo, "second", 2, series="second")
    removed_ids = [first.id, second.id]
    delayed = _ops(db, repo, removed_ids)
    delayed_id = delayed.id
    repository_id = repo.id
    if partially_merged:
        ctx = _ctx(db, repo, delayed)
        ctx.progress.side_effect = RuntimeError("progress unavailable")
        with pytest.raises(RuntimeError, match="progress unavailable"):
            await history.run_history_merge(ctx)
    # Another chain runs before this merge first starts, or during its retry
    # backoff. Its listing rediscovers and its merge deletes the remaining rows.
    _, remaining = index_exec.apply_listing(db, repo, [], timezone_name="UTC")
    overtaking = _ops(db, repo, remaining)
    await history.run_history_merge(_ctx(db, repo, overtaking))
    first_new = _archive(db, repo, "first-new", 3)
    second_new = _archive(db, repo, "second-new", 4)
    assert [first_new.id, second_new.id] == removed_ids
    _row(db, second_new, "keep", "added", after=9)
    db.rollback()
    db.expunge_all()
    repo = db.get(Repository, repository_id)
    delayed = db.get(Operation, delayed_id)

    out = await history.run_history_merge(_ctx(db, repo, delayed))

    assert [a.borg_id for a in db.query(Archive).order_by(Archive.id)] == [
        "id-first-new",
        "id-second-new",
    ]
    assert db.query(ArchiveChange).one().path == "keep"
    assert out.result["merged"] == int(partially_merged)


@pytest.mark.unit
@pytest.mark.parametrize(
    "missing_identity",
    [
        "removed_archive_borg_ids",
        "removed_archive_last_seen_at",
        "removed_archive_generations",
    ],
)
async def test_legacy_targets_wait_for_a_listing_with_complete_identities(
    db, repo, missing_identity
):
    removed = _archive(db, repo, "removed", 1)
    removed_id = removed.id
    legacy = _ops(db, repo, [removed_id])
    parent = db.get(Operation, legacy.depends_on_id)
    parent.result = {k: v for k, v in parent.result.items() if k != missing_identity}
    db.commit()

    out = await history.run_history_merge(_ctx(db, repo, legacy))

    assert out.result["merged"] == 0
    assert db.get(Archive, removed_id) is not None
    _, rediscovered = index_exec.apply_listing(db, repo, [], timezone_name="UTC")
    assert rediscovered == [removed_id]
    followup = _ops(db, repo, rediscovered)
    out = await history.run_history_merge(_ctx(db, repo, followup))
    assert out.result["merged"] == 1
    assert db.get(Archive, removed_id) is None


@pytest.mark.unit
@pytest.mark.parametrize("partially_merged", [False, True])
@pytest.mark.parametrize("clock_delta", [-1, 0, 1])
async def test_delayed_merge_preserves_rediscovered_archive(
    db, repo, monkeypatch, partially_merged, clock_delta
):
    first = _archive(db, repo, "first", 1, series="first")
    revived = _archive(db, repo, "revived", 2, series="revived")
    revived_id = revived.id
    last_seen = datetime(2026, 9, 10, 12)
    revived.last_seen_at = last_seen
    db.commit()
    _row(db, revived, "keep", "added", after=9)
    delayed = _ops(db, repo, [first.id, revived_id])
    if partially_merged:
        ctx = _ctx(db, repo, delayed)
        ctx.progress.side_effect = RuntimeError("progress unavailable")
        with pytest.raises(RuntimeError, match="progress unavailable"):
            await history.run_history_merge(ctx)

    # A later successful listing sees the same archive in the same DB row.
    # Its observation must invalidate deletion even if wall time is unchanged
    # or moves backward, and even when the merge is resuming after a failure.
    monkeypatch.setattr(
        index_exec, "utc_now", lambda: last_seen + timedelta(seconds=clock_delta)
    )
    index_exec.apply_listing(
        db,
        repo,
        [
            {
                "id": revived.borg_id,
                "name": "revived",
                "start": revived.start.isoformat(),
            }
        ],
        timezone_name="UTC",
    )
    db.expire_all()

    for _ in range(2):
        out = await history.run_history_merge(_ctx(db, repo, delayed))
        assert db.get(Archive, revived_id) is not None
        assert (
            db.query(ArchiveChange).filter_by(archive_id=revived_id).one().path
            == "keep"
        )
        assert out.result["merged"] == 1

    # A fresh absence observation may still legitimately remove it later.
    _, absent = index_exec.apply_listing(db, repo, [], timezone_name="UTC")
    followup = _ops(db, repo, absent)
    out = await history.run_history_merge(_ctx(db, repo, followup))
    assert out.result["merged"] == 1
    assert db.get(Archive, revived_id) is None


@pytest.mark.unit
@pytest.mark.parametrize("partially_merged", [False, True])
async def test_delayed_merge_preserves_recreated_archive_with_identical_timestamps(
    db, repo, monkeypatch, partially_merged
):
    first = _archive(db, repo, "first", 1, series="first")
    old = _archive(db, repo, "recreated", 2, series="recreated")
    old_id = old.id
    captured_time = datetime(2026, 9, 12, 12)
    old.last_seen_at = captured_time
    db.commit()
    delayed = _ops(db, repo, [first.id, old_id])
    if partially_merged:
        ctx = _ctx(db, repo, delayed)
        ctx.progress.side_effect = RuntimeError("progress unavailable")
        with pytest.raises(RuntimeError, match="progress unavailable"):
            await history.run_history_merge(ctx)

    _, absent = index_exec.apply_listing(db, repo, [], timezone_name="UTC")
    overtaking = _ops(db, repo, absent)
    await history.run_history_merge(_ctx(db, repo, overtaking))
    monkeypatch.setattr(index_exec, "utc_now", lambda: captured_time)
    index_exec.apply_listing(
        db,
        repo,
        [
            {"id": "id-first-new", "name": "first-new", "start": "2026-09-01T02:00:00"},
            {
                "id": "id-recreated",
                "name": "recreated",
                "start": "2026-09-02T02:00:00",
                "comment": "new metadata",
            },
        ],
        timezone_name="UTC",
    )
    replacement = db.query(Archive).filter_by(borg_id="id-recreated").one()
    assert replacement.id == old_id
    assert replacement.last_seen_at == captured_time
    _row(db, replacement, "keep", "added", after=9)
    db.expire_all()

    for _ in range(2):
        await history.run_history_merge(_ctx(db, repo, delayed))
        replacement = db.get(Archive, old_id)
        assert replacement is not None
        assert replacement.comment == "new metadata"
        assert db.query(ArchiveChange).filter_by(archive_id=old_id).one().path == "keep"
