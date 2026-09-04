from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, ArchiveChange, Base, Repository, SystemSettings
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


def _archive(db, repo, name, day, series="nas", state="pending", borg_id=None):
    a = Archive(
        repository_id=repo.id,
        borg_id=borg_id or f"id-{name}",
        name=name,
        series=series,
        start=datetime(2026, 9, day, 2, 0, 0),
        history_state=state,
    )
    db.add(a)
    db.commit()
    return a


def _ctx(db, repo, cancelled=False):
    return SimpleNamespace(
        db=db,
        repository_id=repo.id,
        operation_id=1,
        kind="history_index",
        params={},
        operation=SimpleNamespace(depends_on_id=None),
        progress=AsyncMock(),
        log=lambda line: None,
        cancelled=lambda: cancelled,
    )


class FakeStream:
    def __init__(self, lines, return_code=0, stderr=""):
        self._lines = lines
        self.return_code = None
        self.stderr = ""
        self._rc = return_code
        self._stderr = stderr
        self.closed = False

    async def __aiter__(self):
        for line in self._lines:
            yield line
        self.return_code = self._rc
        self.stderr = self._stderr

    async def close(self):
        self.closed = True
        self.return_code = -9


class FakeRouter:
    """Maps (a, b) diff refs and list refs to canned lines."""

    lists: dict = {}
    diffs: dict = {}

    def __init__(self, repository):
        self.repository = repository

    def list_archive_lines(self, archive, *, env=None, timeout=3600):
        return FakeStream(self.lists[archive])

    def diff_archives(self, a, b, *, env=None, timeout=3600):
        value = self.diffs[(a, b)]
        return value if isinstance(value, FakeStream) else FakeStream(value)


def L(path, size=None, t="-"):
    return f'{{"type": "{t}", "path": "{path}", "size": {size if size is not None else "null"}}}'


def D_MOD(path, added, removed):
    return (
        f'{{"path": "{path}", "changes": '
        f'[{{"type": "modified", "added": {added}, "removed": {removed}}}]}}'
    )


def D_ADD(path, size):
    return f'{{"path": "{path}", "changes": [{{"type": "added", "size": {size}}}]}}'


def D_RM(path, size):
    return f'{{"path": "{path}", "changes": [{{"type": "removed", "size": {size}}}]}}'


@pytest.fixture(autouse=True)
def _patches():
    with (
        patch.object(history, "_prepare_repository_borg_env", return_value=({}, None)),
        patch.object(history, "BorgRouter", FakeRouter),
        patch.object(history, "history_enabled", return_value=True),
    ):
        FakeRouter.lists = {}
        FakeRouter.diffs = {}
        yield


@pytest.mark.unit
def test_glob_excludes():
    compiled = history.compile_excludes(
        ["**/node_modules/**", "*.log", "home/*/tmp/**"]
    )
    assert history.is_excluded("app/node_modules/x/y.js", compiled)
    assert history.is_excluded("node_modules/y.js", compiled)
    assert history.is_excluded("a.log", compiled)
    assert not history.is_excluded("dir/a.log", compiled)
    assert history.is_excluded("home/k/tmp/f", compiled)
    assert not history.is_excluded("home/k/tmp", compiled)
    assert history.compile_excludes([]) == []


@pytest.mark.unit
def test_default_excludes_match_at_root_and_nested():
    from app.database.models import DEFAULT_HISTORY_INDEX_EXCLUDES

    compiled = history.compile_excludes(DEFAULT_HISTORY_INDEX_EXCLUDES)
    assert history.is_excluded(".cache/blob", compiled)
    assert history.is_excluded("home/k/.git/objects/ab/cd", compiled)
    assert not history.is_excluded("home/k/.git/HEAD", compiled)
    assert not history.is_excluded("home/k/cache/file", compiled)


@pytest.mark.unit
def test_summary_prefix():
    assert history.summary_prefix("a/b/c/d/e") == "a/b/c"
    assert history.summary_prefix("a") == "a"


@pytest.mark.unit
async def test_first_archive_gets_full_listing_without_directories_or_excludes(
    db, repo
):
    a1 = _archive(db, repo, "first", 1)
    FakeRouter.lists["first"] = [
        L("src", t="d"),
        L("src/a.txt", 5),
        L("src/.cache/x", 1),
        L("src/link", t="l"),
    ]
    out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "completed"
    assert out.result == {"indexed": 1, "failed": 0, "left_pending": 0}
    db.refresh(a1)
    assert a1.history_state == "indexed"
    assert a1.history_rows == 2
    assert a1.history_truncated is False
    assert a1.history_indexed_at is not None
    rows = {r.path: r for r in db.query(ArchiveChange).filter_by(archive_id=a1.id)}
    assert set(rows) == {"src/a.txt", "src/link"}
    assert rows["src/a.txt"].change == "added" and rows["src/a.txt"].size_after == 5
    assert rows["src/link"].size_after is None


@pytest.mark.unit
async def test_pair_diff_resolves_sizes_from_last_known(db, repo):
    a1 = _archive(db, repo, "first", 1, state="indexed")
    db.add(
        ArchiveChange(archive_id=a1.id, path="src/a.txt", change="added", size_after=10)
    )
    db.commit()
    a2 = _archive(db, repo, "second", 2)
    FakeRouter.diffs[("first", "second")] = [
        D_MOD("src/a.txt", 7, 2),
        D_ADD("src/n.txt", 3),
        D_RM("src/g.txt", 4),
        D_MOD("src/unknown.txt", 1, 0),
    ]
    out = await history.run_history_index(_ctx(db, repo))
    assert out.result["indexed"] == 1
    rows = {r.path: r for r in db.query(ArchiveChange).filter_by(archive_id=a2.id)}
    assert (rows["src/a.txt"].size_before, rows["src/a.txt"].size_after) == (10, 15)
    assert rows["src/n.txt"].size_after == 3 and rows["src/g.txt"].size_before == 4
    assert (
        rows["src/unknown.txt"].size_before,
        rows["src/unknown.txt"].size_after,
    ) == (
        None,
        None,
    )


@pytest.mark.unit
async def test_known_size_comes_from_the_latest_earlier_archive_in_the_series(db, repo):
    a1 = _archive(db, repo, "first", 1, state="indexed")
    a2 = _archive(db, repo, "second", 2, state="indexed")
    other = _archive(db, repo, "other", 3, series="other", state="indexed")
    db.add_all(
        [
            ArchiveChange(archive_id=a1.id, path="f", change="added", size_after=1),
            ArchiveChange(archive_id=a2.id, path="f", change="modified", size_after=2),
            ArchiveChange(archive_id=other.id, path="f", change="added", size_after=99),
        ]
    )
    db.commit()
    a3 = _archive(db, repo, "third", 4)
    sizes = history.known_sizes(db, repo.id, "nas", a3.start, ["f", "missing"])
    assert sizes == {"f": 2}


@pytest.mark.unit
async def test_predecessor_not_indexed_leaves_archive_pending(db, repo):
    a1 = _archive(db, repo, "first", 1)
    a2 = _archive(db, repo, "second", 2)
    # "first" fails in this run, so "second" has no indexed predecessor to diff
    # against and stays pending.
    FakeRouter.lists["first"] = FakeStream([L("a", 1)], return_code=2, stderr="boom")
    out = await history.run_history_index(_ctx(db, repo))
    assert out.result == {"indexed": 0, "failed": 1, "left_pending": 1}
    db.refresh(a1)
    db.refresh(a2)
    assert a1.history_state == "failed"
    assert a2.history_state == "pending"


@pytest.mark.unit
async def test_a_failed_archive_is_retried_on_the_next_run(db, repo):
    """Nothing else moves an archive out of "failed", so a run that skipped it
    would stall the whole series for good: every later archive would fail the
    indexed-predecessor check forever."""
    a1 = _archive(db, repo, "first", 1, state="failed")
    a2 = _archive(db, repo, "second", 2)
    FakeRouter.lists["first"] = [L("a", 1)]
    FakeRouter.diffs[("first", "second")] = [D_ADD("b", 2)]

    out = await history.run_history_index(_ctx(db, repo))

    assert out.status == "completed"
    assert out.result == {"indexed": 2, "failed": 0, "left_pending": 0}
    db.refresh(a1)
    db.refresh(a2)
    assert a1.history_state == "indexed" and a2.history_state == "indexed"


@pytest.mark.unit
async def test_archives_left_pending_report_a_warning_status(db, repo):
    """A run that indexed nothing because a predecessor is not indexed must not
    look like a clean success."""
    _archive(db, repo, "first", 1, state="skipped")
    _archive(db, repo, "second", 2)

    out = await history.run_history_index(_ctx(db, repo))

    assert out.status == "completed_with_warnings"
    assert out.result == {"indexed": 0, "failed": 0, "left_pending": 1}


@pytest.mark.unit
async def test_two_pending_archives_index_in_order_within_one_run(db, repo):
    _archive(db, repo, "first", 1)
    a2 = _archive(db, repo, "second", 2)
    FakeRouter.lists["first"] = [L("a", 1)]
    FakeRouter.diffs[("first", "second")] = [D_MOD("a", 4, 0)]
    out = await history.run_history_index(_ctx(db, repo))
    assert out.result == {"indexed": 2, "failed": 0, "left_pending": 0}
    row = db.query(ArchiveChange).filter_by(archive_id=a2.id).one()
    assert (row.size_before, row.size_after) == (1, 5)


@pytest.mark.unit
async def test_cap_collapses_overflow_into_summary_rows(db, repo, monkeypatch):
    monkeypatch.setattr(history.settings, "index_history_max_rows", 2)
    a1 = _archive(db, repo, "first", 1)
    FakeRouter.lists["first"] = [
        L("a/b/c/1", 1),
        L("a/b/c/2", 1),
        L("a/b/c/3", 1),
        L("a/b/d/4", 1),
        L("x", 1),
    ]
    await history.run_history_index(_ctx(db, repo))
    db.refresh(a1)
    assert a1.history_truncated is True and a1.history_rows == 5
    summaries = {
        r.path: r.summary_count
        for r in db.query(ArchiveChange).filter_by(archive_id=a1.id, change="summary")
    }
    assert summaries == {"a/b/c": 1, "a/b/d": 1, "x": 1}
    detail = (
        db.query(ArchiveChange)
        .filter_by(archive_id=a1.id)
        .filter(ArchiveChange.change != "summary")
        .count()
    )
    assert detail == 2


@pytest.mark.unit
async def test_agent_repository_skips_all_pending(db, repo):
    a1 = _archive(db, repo, "first", 1)
    with patch.object(history, "is_agent_executor", return_value=True):
        out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "skipped" and out.skip_reason == "agent_diff_unsupported"
    db.refresh(a1)
    assert a1.history_state == "skipped"


@pytest.mark.unit
async def test_plan_locked_skips_without_touching_archives(db, repo):
    a1 = _archive(db, repo, "first", 1)
    with patch.object(history, "history_enabled", return_value=False):
        out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "skipped" and out.skip_reason == "plan_locked"
    db.refresh(a1)
    assert a1.history_state == "pending"


@pytest.mark.unit
async def test_borg_failure_marks_archive_failed_and_warns(db, repo):
    _archive(db, repo, "first", 1, state="indexed")
    a2 = _archive(db, repo, "second", 2)
    FakeRouter.diffs[("first", "second")] = FakeStream(
        [D_ADD("x", 1)], return_code=2, stderr="lock held"
    )
    out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "completed_with_warnings" and out.result["failed"] == 1
    db.refresh(a2)
    assert a2.history_state == "failed"
    assert db.query(ArchiveChange).filter_by(archive_id=a2.id).count() == 0


@pytest.mark.unit
async def test_borg_warning_exit_code_still_indexes(db, repo):
    _archive(db, repo, "first", 1, state="indexed")
    a2 = _archive(db, repo, "second", 2)
    FakeRouter.diffs[("first", "second")] = FakeStream([D_ADD("x", 1)], return_code=1)
    out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "completed" and out.result["indexed"] == 1
    db.refresh(a2)
    assert a2.history_state == "indexed"


@pytest.mark.unit
async def test_cancel_stops_between_archives(db, repo):
    _archive(db, repo, "first", 1)
    FakeRouter.lists["first"] = [L("a", 1)]
    out = await history.run_history_index(_ctx(db, repo, cancelled=True))
    assert out.result["indexed"] == 0


@pytest.mark.unit
async def test_cancel_mid_stream_closes_stream_and_keeps_archive_pending(db, repo):
    a1 = _archive(db, repo, "first", 1)
    stream = FakeStream([L("a", 1), L("b", 1)])
    flags = iter([False, True, True, True])
    ctx = _ctx(db, repo)
    ctx.cancelled = lambda: next(flags)
    with patch.object(
        FakeRouter, "list_archive_lines", lambda self, archive, **kw: stream
    ):
        out = await history.run_history_index(ctx)
    assert out.result["indexed"] == 0
    assert stream.closed is True
    db.refresh(a1)
    assert a1.history_state == "pending"
    assert db.query(ArchiveChange).count() == 0


@pytest.mark.unit
async def test_borg2_uses_aid_references(db, repo):
    repo.borg_version = 2
    db.commit()
    a1 = _archive(db, repo, "nas", 1, state="indexed", borg_id="aa11")
    a2 = _archive(db, repo, "nas", 2, borg_id="bb22")
    FakeRouter.diffs[(f"aid:{a1.borg_id}", f"aid:{a2.borg_id}")] = [D_ADD("x", 1)]
    out = await history.run_history_index(_ctx(db, repo))
    assert out.result["indexed"] == 1


@pytest.mark.unit
async def test_progress_reports_pair_label(db, repo):
    _archive(db, repo, "first", 1, state="indexed")
    _archive(db, repo, "second", 2)
    FakeRouter.diffs[("first", "second")] = []
    ctx = _ctx(db, repo)
    await history.run_history_index(ctx)
    messages = [c.kwargs.get("message") for c in ctx.progress.await_args_list]
    assert "first → second" in messages


@pytest.mark.unit
async def test_reindex_replaces_previous_rows(db, repo):
    a1 = _archive(db, repo, "first", 1)
    db.add(ArchiveChange(archive_id=a1.id, path="stale", change="added", size_after=1))
    db.commit()
    FakeRouter.lists["first"] = [L("fresh", 2)]
    await history.run_history_index(_ctx(db, repo))
    assert {r.path for r in db.query(ArchiveChange).filter_by(archive_id=a1.id)} == {
        "fresh"
    }


@pytest.mark.unit
def test_registered():
    from app.services.operations.executors import (
        load_default_executors,
        registered_kinds,
    )

    load_default_executors()
    assert {"history_index", "history_merge"} <= registered_kinds()


@pytest.mark.unit
def test_null_excludes_fall_back_to_the_defaults():
    """A row that predates the column reads back as the defaults through the
    API, so the indexer has to apply the same fallback. An explicit empty list
    still means "exclude nothing"."""
    from app.database.models import DEFAULT_HISTORY_INDEX_EXCLUDES

    compiled = history.compile_excludes(None)
    assert len(compiled) == len(DEFAULT_HISTORY_INDEX_EXCLUDES)
    assert history.is_excluded("home/u/.cache/pip/x", compiled) is True

    assert history.compile_excludes([]) == []
