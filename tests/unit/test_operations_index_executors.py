import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, Base, Repository, SystemSettings
from app.services.operations.executors import index as index_exec
from app.services.operations.runner import Outcome
from app.services.storage_usage import SizeResult


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


def _ctx(db, repo, kind="archive_sync"):
    progress = AsyncMock()
    return SimpleNamespace(
        db=db,
        repository_id=repo.id,
        operation_id=1,
        kind=kind,
        params={},
        progress=progress,
        log=lambda line: None,
        cancelled=lambda: False,
    )


BORG1_ENTRY = {
    "archive": "nas-2026-09-02T02:00:00",
    "name": "nas-2026-09-02T02:00:00",
    "id": "aa11",
    "start": "2026-09-02T02:00:00.000000",
    "time": "2026-09-02T02:00:00.000000",
}
BORG2_ENTRY = {
    "name": "nas",
    "id": "bb22",
    "time": "2026-09-02T02:00:00.000000",
    "hostname": "nas",
    "username": "root",
    "comment": "",
}


@pytest.mark.unit
def test_archive_fields_from_listing_borg1_and_borg2():
    f1 = index_exec.archive_fields_from_listing(BORG1_ENTRY, 1, timezone_name="UTC")
    assert f1["borg_id"] == "aa11"
    assert f1["name"] == "nas-2026-09-02T02:00:00"
    assert f1["series"] == "nas"
    assert f1["start"] == datetime(2026, 9, 2, 2, 0, 0)
    f1p = index_exec.archive_fields_from_listing(
        BORG1_ENTRY, 1, timezone_name="UTC", series_prefixes=["nas"]
    )
    assert f1p["series"] == "nas"
    f2 = index_exec.archive_fields_from_listing(BORG2_ENTRY, 2, timezone_name="UTC")
    assert f2["series"] == "nas"
    assert f2["hostname"] == "nas" and f2["username"] == "root"
    assert (
        index_exec.archive_fields_from_listing({"name": "x"}, 1, timezone_name="UTC")
        is None
    )
    assert (
        index_exec.archive_fields_from_listing(
            {"id": "x", "name": "n"}, 2, timezone_name="UTC"
        )
        is None
    )


@pytest.mark.unit
def test_archive_fields_from_listing_converts_wall_clock_zone_to_utc():
    """Borg renders naive wall-clock times in the listing zone; the stored
    value is naive UTC, so a Berlin 02:00 in September is 00:00 UTC."""
    fields = index_exec.archive_fields_from_listing(
        BORG1_ENTRY, 1, timezone_name="Europe/Berlin"
    )
    assert fields["start"] == datetime(2026, 9, 2, 0, 0, 0)


@pytest.mark.unit
def test_apply_listing_upserts_and_reports_removed(db, repo):
    gone = Archive(
        repository_id=repo.id,
        borg_id="old",
        name="old",
        series="default",
        start=datetime(2026, 8, 1),
    )
    db.add(gone)
    db.commit()
    new_rows, removed = index_exec.apply_listing(
        db, repo, [BORG1_ENTRY], timezone_name="UTC"
    )
    assert [a.borg_id for a in new_rows] == ["aa11"]
    assert removed == [gone.id]
    assert db.query(Archive).count() == 2
    again_new, again_removed = index_exec.apply_listing(
        db, repo, [BORG1_ENTRY], timezone_name="UTC"
    )
    assert again_new == [] and again_removed == [gone.id]
    row = db.query(Archive).filter_by(borg_id="aa11").one()
    assert row.last_seen_at >= row.first_seen_at


@pytest.mark.unit
def test_apply_listing_keeps_the_info_filled_end(db, repo):
    """`borg list --json` has no end (only `borg info` does): a resync must
    not wipe the end fill_archive_info stored, or every run refills it."""
    index_exec.apply_listing(db, repo, [BORG1_ENTRY], timezone_name="UTC")
    row = db.query(Archive).filter_by(borg_id="aa11").one()
    row.end = datetime(2026, 9, 2, 2, 10)
    db.commit()
    index_exec.apply_listing(db, repo, [BORG1_ENTRY], timezone_name="UTC")
    db.expire_all()
    assert db.query(Archive).filter_by(borg_id="aa11").one().end == datetime(
        2026, 9, 2, 2, 10
    )


@pytest.mark.unit
def test_apply_listing_series_change_resets_history_state(db, repo):
    repo.borg_version = 2
    db.commit()
    existing = Archive(
        repository_id=repo.id,
        borg_id="bb22",
        name="old-series",
        series="old-series",
        start=datetime(2026, 8, 1),
        history_state="indexed",
    )
    db.add(existing)
    db.commit()
    index_exec.apply_listing(db, repo, [BORG2_ENTRY], timezone_name="UTC")
    db.refresh(existing)
    assert existing.series == "nas"
    assert existing.history_state == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_updates_repository_columns(db, repo, monkeypatch):
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(True, [BORG1_ENTRY], "UTC")),
    )
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=1))
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    ctx = _ctx(db, repo)
    outcome = await index_exec.run_archive_sync(ctx)
    assert isinstance(outcome, Outcome)
    assert outcome.result == {
        "listed": 1,
        "new": 1,
        "info_filled": 1,
        "removed_archive_ids": [],
    }
    db.refresh(repo)
    assert repo.archive_count == 1
    assert repo.last_backup == datetime(2026, 9, 2, 2, 0, 0)
    ctx.progress.assert_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent, plan_has_history, expected_state",
    [
        (True, True, "skipped"),  # no history run reaches it: say so
        (
            True,
            False,
            "skipped",
        ),  # on Community too: the executor's reason outlasts the plan
        (False, True, "pending"),  # server-side: the history run decides
        (False, False, "pending"),  # Community: the stage is absent, nothing is touched
    ],
)
async def test_run_archive_sync_marks_agent_archives_skipped(
    db, repo, monkeypatch, agent, plan_has_history, expected_state
):
    """No history run reaches an agent's repository on any plan, so the
    listing writes the state that run used to write: a new archive is
    `skipped`, not a `pending` that reads as "not yet"; an indexed one is
    left alone. On a server's repository `pending` stays, so the history
    run (or a later plan change) finds it."""
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(True, [BORG1_ENTRY], "UTC")),
    )
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=0))
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(
        "app.services.repository_executor.is_agent_executor", lambda repository: agent
    )
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: agent)
    monkeypatch.setattr(
        "app.services.operations.followups.history_enabled",
        lambda db: plan_has_history,
    )
    # a Borg 1 listing needs a way to resolve archive ends; not this test's point
    monkeypatch.setattr(
        index_exec, "archive_end_resolvable", lambda db, repository: True
    )
    earlier = Archive(
        repository_id=repo.id,
        borg_id="earlier",
        name="earlier",
        series="nas",
        start=datetime(2026, 9, 1, 2),
        history_state="indexed",
    )
    given_up = Archive(
        repository_id=repo.id,
        borg_id="given-up",
        name="given-up",
        series="nas",
        start=datetime(2026, 9, 1, 3),
        history_state="failed",
    )
    leftover = Archive(
        repository_id=repo.id,
        borg_id="leftover",
        name="leftover",
        series="nas",
        start=datetime(2026, 9, 1, 4),
        history_state="skipped",
        history_attempts=3,
    )
    other_repo = Repository(
        name="other", path="/tmp/other", encryption="none", compression="lz4"
    )
    db.add_all([earlier, given_up, leftover, other_repo])
    db.flush()
    db.add(
        Archive(
            repository_id=other_repo.id,
            borg_id="elsewhere",
            name="elsewhere",
            series="nas",
            start=datetime(2026, 9, 1, 2),
            history_state="pending",
        )
    )
    db.commit()

    await index_exec.run_archive_sync(_ctx(db, repo))

    db.expire_all()
    states = {a.name: a.history_state for a in db.query(Archive).all()}
    assert states.pop("earlier") == "indexed"
    assert states.pop("elsewhere") == "pending"  # another repository's row
    # a failure is marked with the rest where the listing marks, kept otherwise
    assert states.pop("given-up") == (
        "skipped" if expected_state == "skipped" else "failed"
    )
    # a `skipped` row on a server's repository is left over from an
    # agent-executed past: reopened with a fresh budget where the history
    # stage exists, left alone everywhere else
    reopened = not agent and plan_has_history
    assert states.pop("leftover") == ("pending" if reopened else "skipped")
    assert db.query(Archive).filter_by(name="leftover").one().history_attempts == (
        0 if reopened else 3
    )
    assert states and all(state == expected_state for state in states.values())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_clears_last_backup_when_no_archives_remain(
    db, repo, monkeypatch
):
    repo.archive_count = 1
    repo.last_backup = datetime(2026, 9, 2, 2, 0, 0)
    db.add(
        Archive(
            repository_id=repo.id,
            borg_id="aa11",
            name="nas-2026-09-02",
            series="default",
            start=datetime(2026, 9, 2, 2, 0, 0),
        )
    )
    db.commit()
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(True, [], "UTC")),
    )
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=0))
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    await index_exec.run_archive_sync(_ctx(db, repo))
    db.refresh(repo)
    assert repo.archive_count == 0
    assert repo.last_backup is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_skips_missing_repository(db, repo):
    ctx = _ctx(db, repo)
    ctx.repository_id = 9999
    outcome = await index_exec.run_archive_sync(ctx)
    assert outcome.status == "skipped" and outcome.skip_reason == "repository_missing"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_writes_total_size(db, repo, monkeypatch):
    """stats persists the measured size with its source and Borg's
    last_modified (#934)."""
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(
        index_exec,
        "measure_repository_size",
        AsyncMock(
            return_value=SizeResult(
                bytes=2048,
                objects=3,
                source="borg2_index",
                last_modified=datetime(2026, 9, 6, 8, 57, 17),
            )
        ),
    )
    outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.result == {
        "bytes": 2048,
        "objects": 3,
        "source": "borg2_index",
        "last_modified": "2026-09-06T08:57:17",
    }
    db.refresh(repo)
    assert repo.total_size == "2.00 KB"
    assert repo.total_size_bytes == 2048
    assert repo.total_size_measured_at is not None
    assert repo.total_size_source == "borg2_index"
    assert repo.borg_last_modified == datetime(2026, 9, 6, 8, 57, 17)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_leaves_size_alone_when_unknown(db, repo, monkeypatch):
    repo.total_size = "keep"
    repo.total_size_source = "borg1_cache_stats"
    db.commit()
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(
        index_exec, "measure_repository_size", AsyncMock(return_value=SizeResult())
    )
    outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.status == "completed" and outcome.result["bytes"] is None
    db.refresh(repo)
    assert repo.total_size == "keep" and repo.total_size_source == "borg1_cache_stats"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_persists_last_modified_when_the_size_is_unknown(
    db, repo, monkeypatch
):
    """Borg 2 with `repo-info` working but no index and no store measurement:
    the size stays as it was, `last_modified` is still written."""
    from datetime import datetime

    repo.total_size = "keep"
    repo.total_size_source = "borg1_cache_stats"
    db.commit()
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(
        index_exec,
        "measure_repository_size",
        AsyncMock(return_value=SizeResult(last_modified=datetime(2026, 9, 7, 8, 0))),
    )
    outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.status == "completed"
    assert outcome.result["bytes"] is None
    assert outcome.result["last_modified"] == "2026-09-07T08:00:00"
    db.refresh(repo)
    assert repo.total_size == "keep" and repo.total_size_source == "borg1_cache_stats"
    assert repo.borg_last_modified == datetime(2026, 9, 7, 8, 0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_agent_repository_leaves_size_alone_when_unmeasurable(
    db, repo, monkeypatch
):
    """The agent path decides what it can measure; a repository it cannot size
    keeps the stored value rather than losing it."""
    repo.total_size = "keep"
    db.commit()
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )

    async def fake_update(repository, session, **kwargs):
        assert kwargs == {"raise_busy": True}
        return True

    monkeypatch.setattr(
        "app.api.repositories._update_agent_repository_stats", fake_update
    )
    with patch.object(index_exec, "_publish_mqtt_state"):
        outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.result == {"total_size": "keep", "executor": "agent"}
    db.refresh(repo)
    assert repo.total_size == "keep"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_limits_and_orders_oldest_first(db, repo, monkeypatch):
    rows = []
    for i, day in enumerate((3, 1, 2)):
        a = Archive(
            repository_id=repo.id,
            borg_id=f"id{i}",
            name=f"n{i}",
            series="default",
            start=datetime(2026, 9, day),
        )
        db.add(a)
        rows.append(a)
    db.commit()
    seen = []

    async def fake_info(repository, archive_name, **kwargs):
        seen.append(archive_name)
        assert kwargs["env"]["TZ"] == "UTC"
        return {
            "success": True,
            "stdout": json.dumps(
                {
                    "archives": [
                        {
                            "stats": {
                                "nfiles": 5,
                                "original_size": 10,
                                "compressed_size": 8,
                                "deduplicated_size": 4,
                            },
                            "end": "2026-09-01T02:10:00.000000",
                            "duration": 600.0,
                        }
                    ]
                }
            ),
        }

    monkeypatch.setattr("app.core.borg.borg.info_archive", fake_info)
    filled = await index_exec.fill_archive_info(db, repo, rows, {}, limit=2)
    assert filled == 2
    assert seen == ["n1", "n2"]
    db.expire_all()
    oldest = db.query(Archive).filter_by(borg_id="id1").one()
    assert oldest.nfiles == 5 and oldest.deduplicated_size == 4
    assert oldest.duration_seconds == 600.0
    newest = db.query(Archive).filter_by(borg_id="id0").one()
    assert newest.nfiles is None


def _agent_info_payload(end="2026-09-01T02:10:00.000000"):
    return json.dumps(
        {
            "archives": [
                {
                    "stats": {"nfiles": 7, "original_size": 20},
                    "end": end,
                    "duration": 30.0,
                }
            ]
        }
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_dispatches_agent_job(db, repo, monkeypatch):
    """Agent repositories fill per-archive info through the agent's
    `repository.archive_info` job (#932): Borg 2 archives by `aid:<id>`, the
    agent's reported zone resolves naive end times, a failed job is skipped."""
    repo.borg_version = 2
    db.commit()
    rows = []
    for i in range(3):
        a = Archive(
            repository_id=repo.id,
            borg_id=f"id{i}",
            name="series",
            series="series",
            start=datetime(2026, 9, i + 1),
        )
        db.add(a)
        rows.append(a)
    db.commit()
    queued = []

    def fake_queue(db_, repository, *, job_kind, operation=None):
        queued.append((job_kind, operation["archive"]))
        return SimpleNamespace(id=len(queued))

    async def fake_wait(db_, job_id, *, timeout_seconds):
        assert timeout_seconds == 42
        if job_id == 2:
            return {"return_code": 2, "stdout": "", "stderr": "borg: lock"}
        return {"return_code": 0, "stdout": _agent_info_payload()}

    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: "Europe/Berlin"
    )
    monkeypatch.setattr(
        index_exec, "get_operation_timeouts", lambda db_: {"info_timeout": 42}
    )
    monkeypatch.setattr(
        "app.services.repository_executor.queue_agent_repository_operation_job",
        fake_queue,
    )
    monkeypatch.setattr(
        "app.services.repository_executor.wait_for_agent_repository_operation_job",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
        AsyncMock(return_value=True),
    )
    filled = await index_exec.fill_archive_info(db, repo, rows, {}, limit=3)
    assert filled == 2
    assert queued == [
        ("repository.archive_info", "aid:id0"),
        ("repository.archive_info", "aid:id1"),
        ("repository.archive_info", "aid:id2"),
    ]
    db.expire_all()
    first = db.query(Archive).filter_by(borg_id="id0").one()
    assert first.nfiles == 7 and first.original_size == 20
    assert first.compressed_size is None and first.deduplicated_size is None
    assert first.duration_seconds == 30.0
    # 02:10 Berlin summer time is 00:10 UTC
    assert first.end == datetime(2026, 9, 1, 0, 10)
    failed = db.query(Archive).filter_by(borg_id="id1").one()
    assert failed.nfiles is None and failed.end is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_agent_without_zone_leaves_naive_end_unset(
    db, repo, monkeypatch
):
    """An agent that never reported its zone renders Borg 1 end times in an
    unknown wall clock; storing them in the server's zone would shift them.
    Offset-carrying (Borg 2) values are still stored."""
    rows = []
    for i, end in enumerate(
        ("2026-09-01T02:10:00.000000", "2026-09-02T02:10:00.000000+02:00")
    ):
        a = Archive(
            repository_id=repo.id,
            borg_id=f"id{i}",
            name=f"n{i}",
            series="n",
            start=datetime(2026, 9, i + 1),
        )
        db.add(a)
        rows.append((a, end))
    db.commit()
    ends = {f"n{i}": end for i, (_, end) in enumerate(rows)}

    def fake_queue(db_, repository, *, job_kind, operation=None):
        return SimpleNamespace(id=operation["archive"])

    async def fake_wait(db_, job_id, *, timeout_seconds):
        return {"return_code": 0, "stdout": _agent_info_payload(end=ends[job_id])}

    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: None
    )
    monkeypatch.setattr(
        index_exec, "get_operation_timeouts", lambda db_: {"info_timeout": 5}
    )
    monkeypatch.setattr(
        "app.services.repository_executor.queue_agent_repository_operation_job",
        fake_queue,
    )
    monkeypatch.setattr(
        "app.services.repository_executor.wait_for_agent_repository_operation_job",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
        AsyncMock(return_value=True),
    )
    assert (
        await index_exec.fill_archive_info(db, repo, [a for a, _ in rows], {}, limit=2)
        == 2
    )
    db.expire_all()
    naive = db.query(Archive).filter_by(borg_id="id0").one()
    assert naive.nfiles == 7 and naive.duration_seconds == 30.0
    assert naive.end is None
    aware = db.query(Archive).filter_by(borg_id="id1").one()
    assert aware.end == datetime(2026, 9, 2, 0, 10)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_agent_timeout_abandons_job_and_stops(
    db, repo, monkeypatch
):
    """A job the agent never answers is cancelled instead of left queued:
    queued jobs are never reaped and would count as active repository work
    for every later archive_info and stats request (a 409 per archive). The
    remaining archives are not attempted, each would wait out the timeout."""
    from fastapi import HTTPException

    rows = []
    for i in range(3):
        a = Archive(
            repository_id=repo.id,
            borg_id=f"id{i}",
            name=f"n{i}",
            series="n",
            start=datetime(2026, 9, i + 1),
        )
        db.add(a)
        rows.append(a)
    db.commit()
    queued, abandoned, cancels = [], [], []

    def fake_queue(db_, repository, *, job_kind, operation=None):
        queued.append(operation["archive"])
        return SimpleNamespace(id=len(queued))

    async def fake_wait(db_, job_id, *, timeout_seconds):
        raise HTTPException(
            status_code=504,
            detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
        )

    def fake_abandon(db_, job_id):
        abandoned.append(job_id)
        return SimpleNamespace(id=job_id, status="cancel_requested")

    async def fake_cancel(job):
        cancels.append(job.id)
        return True

    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: "UTC"
    )
    monkeypatch.setattr(
        index_exec, "get_operation_timeouts", lambda db_: {"info_timeout": 5}
    )
    monkeypatch.setattr(
        "app.services.repository_executor.queue_agent_repository_operation_job",
        fake_queue,
    )
    monkeypatch.setattr(
        "app.services.repository_executor.wait_for_agent_repository_operation_job",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.repository_executor.abandon_agent_repository_operation_job",
        fake_abandon,
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
        fake_cancel,
    )
    assert await index_exec.fill_archive_info(db, repo, rows, {}, limit=3) == 0
    assert queued == ["n0"]
    assert abandoned == [1] and cancels == [1]
    db.expire_all()
    assert all(a.nfiles is None for a in db.query(Archive).all())


def _three_archives(db, repo):
    rows = []
    for i in range(3):
        a = Archive(
            repository_id=repo.id,
            borg_id=f"id{i}",
            name=f"n{i}",
            series="n",
            start=datetime(2026, 9, i + 1),
        )
        db.add(a)
        rows.append(a)
    db.commit()
    return rows


def _patch_agent_info(monkeypatch, *, queue, wait, zone="UTC"):
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: zone
    )
    monkeypatch.setattr(
        index_exec, "get_operation_timeouts", lambda db_: {"info_timeout": 5}
    )
    monkeypatch.setattr(
        "app.services.repository_executor.queue_agent_repository_operation_job",
        queue,
    )
    monkeypatch.setattr(
        "app.services.repository_executor.wait_for_agent_repository_operation_job",
        wait,
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
        AsyncMock(return_value=True),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_agent_admission_refusal_skips_one_archive(
    db, repo, monkeypatch
):
    """The admission refuses the job for one archive (another job took the
    repository between two archives): the refusal reaches the runner, which
    defers the whole operation, instead of one refused job per remaining
    archive. What the earlier archives wrote stays in the session for the
    runner's requeue commit. Any other failure still skips just that archive."""
    from fastapi import HTTPException

    rows = _three_archives(db, repo)
    queued = []

    def fake_queue(db_, repository, *, job_kind, operation=None):
        queued.append(operation["archive"])
        if len(queued) == 2:
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.jobs.repositoryOperationActive"},
            )
        if len(queued) == 3:
            raise HTTPException(status_code=502, detail="agent gone")
        return SimpleNamespace(id=len(queued))

    async def fake_wait(db_, job_id, *, timeout_seconds):
        return {"return_code": 0, "stdout": _agent_info_payload()}

    _patch_agent_info(monkeypatch, queue=fake_queue, wait=fake_wait)
    with pytest.raises(HTTPException) as info:
        await index_exec.fill_archive_info(db, repo, rows, {}, limit=3)
    assert info.value.status_code == 409
    assert queued == ["n0", "n1"]
    db.commit()
    db.expire_all()
    by_id = {a.borg_id: a for a in db.query(Archive).all()}
    assert by_id["id0"].nfiles == 7
    assert by_id["id1"].nfiles is None and by_id["id2"].nfiles is None

    # a non-busy failure on one archive still leaves the loop running
    queued[:] = ["pad", "pad"]  # n1 becomes the third call: the 502
    assert await index_exec.fill_archive_info(db, repo, rows[1:], {}, limit=2) == 1
    assert queued == ["pad", "pad", "n1", "n2"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_agent_writes_survive_the_next_wait(
    db, repo, monkeypatch
):
    """The real queue commits the session and the real wait expires it on
    every poll. The previous archive's columns are only safe because that
    commit happens between the two; a fake that behaves the same way pins it."""
    rows = _three_archives(db, repo)
    n = {"queued": 0}

    def fake_queue(db_, repository, *, job_kind, operation=None):
        n["queued"] += 1
        db_.commit()
        return SimpleNamespace(id=n["queued"])

    async def fake_wait(db_, job_id, *, timeout_seconds):
        db_.expire_all()
        return {"return_code": 0, "stdout": _agent_info_payload()}

    _patch_agent_info(monkeypatch, queue=fake_queue, wait=fake_wait)
    assert await index_exec.fill_archive_info(db, repo, rows, {}, limit=3) == 3
    db.expire_all()
    assert [a.nfiles for a in db.query(Archive).order_by(Archive.start).all()] == [
        7,
        7,
        7,
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_agent_borg1_uses_archive_name(db, repo, monkeypatch):
    a = Archive(
        repository_id=repo.id,
        borg_id="id0",
        name="nas-2026-09-01",
        series="nas",
        start=datetime(2026, 9, 1),
    )
    db.add(a)
    db.commit()
    seen = []

    def fake_queue(db_, repository, *, job_kind, operation=None):
        seen.append(operation["archive"])
        return SimpleNamespace(id=1)

    async def fake_wait(db_, job_id, *, timeout_seconds):
        return {"return_code": 0, "stdout": _agent_info_payload()}

    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: "UTC"
    )
    monkeypatch.setattr(
        index_exec, "get_operation_timeouts", lambda db_: {"info_timeout": 5}
    )
    monkeypatch.setattr(
        "app.services.repository_executor.queue_agent_repository_operation_job",
        fake_queue,
    )
    monkeypatch.setattr(
        "app.services.repository_executor.wait_for_agent_repository_operation_job",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
        AsyncMock(return_value=True),
    )
    assert await index_exec.fill_archive_info(db, repo, [a], {}, limit=1) == 1
    assert seen == ["nas-2026-09-01"]
    db.expire_all()
    assert db.query(Archive).filter_by(borg_id="id0").one().end == datetime(
        2026, 9, 1, 2, 10
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_refuses_borg1_agent_listing_without_zone(
    db, repo, monkeypatch
):
    """A Borg 1 listing from an agent that never reported its zone would be
    stored in the server's zone, and `start` is NOT NULL so nothing can be
    withheld. The stage fails visibly before any listing runs; Borg 2 renders
    an offset and is unaffected."""
    listing = AsyncMock(return_value=(True, [], "UTC"))
    monkeypatch.setattr(index_exec, "list_archives_for_repository", listing)
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: None
    )
    outcome = await index_exec.run_archive_sync(_ctx(db, repo))
    assert outcome.status == "failed" and "timezone" in outcome.error_message
    listing.assert_not_called()

    repo.borg_version = 2
    db.commit()
    outcome = await index_exec.run_archive_sync(_ctx(db, repo))
    assert outcome.status == "completed"
    listing.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_fails_instead_of_wiping_on_failed_listing(
    db, repo, monkeypatch
):
    """A failed borg listing yields [] just like an empty repository does.
    Writing it would zero archive_count, clear last_backup, and report every
    archive as removed for history_merge to delete."""
    repo.archive_count = 1
    repo.last_backup = datetime(2026, 9, 2, 2, 0, 0)
    db.add(
        Archive(
            repository_id=repo.id,
            borg_id="aa11",
            name="nas-2026-09-02",
            series="default",
            start=datetime(2026, 9, 2, 2, 0, 0),
        )
    )
    db.commit()
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(False, [], "UTC")),
    )
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    outcome = await index_exec.run_archive_sync(_ctx(db, repo))
    assert outcome.status == "failed"
    db.refresh(repo)
    assert repo.archive_count == 1
    assert repo.last_backup == datetime(2026, 9, 2, 2, 0, 0)
    assert db.query(Archive).count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_repository_reports_borg_failure(db, repo, monkeypatch):
    class FailingRouter:
        def __init__(self, repository):
            pass

        async def list_archives_checked(self, env=None):
            return False, []

    monkeypatch.setattr(index_exec, "BorgRouter", FailingRouter)
    ok, entries, zone = await index_exec.list_archives_for_repository(db, repo, {})
    assert ok is False and entries == [] and zone == "UTC"


@pytest.mark.unit
@pytest.mark.parametrize(
    "result,expected",
    [
        ({"return_code": 0, "stdout": "{}"}, True),
        ({"return_code": 2, "stdout": ""}, False),
        ({"success": False, "stdout": ""}, False),
        (None, False),
    ],
)
def test_agent_listing_ok(result, expected):
    assert index_exec._agent_listing_ok(result) is expected


@pytest.mark.unit
def test_archives_needing_info_backfills_across_runs(db, repo):
    """The per-run cap means later runs must pick up archives an earlier run
    left unfilled, not just the rows they created themselves."""
    for i, day in enumerate((1, 2, 3)):
        db.add(
            Archive(
                repository_id=repo.id,
                borg_id=f"id{i}",
                name=f"n{i}",
                series="default",
                start=datetime(2026, 9, day),
                original_size=10 if day == 1 else None,
            )
        )
    db.commit()
    candidates = index_exec.archives_needing_info(db, repo, limit=5)
    assert [a.borg_id for a in candidates] == ["id1", "id2"]
    assert index_exec.archives_needing_info(db, repo, limit=1)[0].borg_id == "id1"
    assert index_exec.archives_needing_info(db, repo, limit=0) == []


@pytest.mark.unit
def test_archives_needing_info_revisits_withheld_end(db, repo, monkeypatch):
    """fill_archive_info sets the sizes but withholds a naive end while the
    agent's zone is unknown. Once the zone is known those rows must come
    back, or their end stays NULL forever; while it is unknown they must
    not, or the same archives are fetched every run for nothing."""
    db.add(
        Archive(
            repository_id=repo.id,
            borg_id="sized",
            name="a",
            series="default",
            start=datetime(2026, 9, 1),
            original_size=10,
            end=None,
        )
    )
    db.add(
        Archive(
            repository_id=repo.id,
            borg_id="done",
            name="b",
            series="default",
            start=datetime(2026, 9, 2),
            original_size=10,
            end=datetime(2026, 9, 2, 1),
        )
    )
    db.add(
        Archive(
            repository_id=repo.id,
            borg_id="fresh",
            name="c",
            series="default",
            start=datetime(2026, 9, 3),
        )
    )
    db.commit()
    ids = lambda rows: [a.borg_id for a in rows]  # noqa: E731
    assert ids(index_exec.archives_needing_info(db, repo, limit=5)) == ["fresh"]
    # rows without stats come first, end-only rows take the spare slots: a
    # row whose end never parses cannot starve an archive without stats
    assert ids(
        index_exec.archives_needing_info(db, repo, limit=5, include_missing_end=True)
    ) == ["fresh", "sized"]
    assert ids(
        index_exec.archives_needing_info(db, repo, limit=1, include_missing_end=True)
    ) == ["fresh"]

    # server repositories always resolve; agent repositories only with a zone
    assert index_exec.archive_end_resolvable(db, repo) is True
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: None
    )
    assert index_exec.archive_end_resolvable(db, repo) is False
    monkeypatch.setattr(
        index_exec, "agent_timezone_for_repository", lambda db_, r: "Europe/Berlin"
    )
    assert index_exec.archive_end_resolvable(db, repo) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_serializes_borg_calls(db, repo, monkeypatch):
    """Per-archive info must take the metadata lock like its siblings, or it
    lands on a repository a backup or check is holding."""
    db.add(
        Archive(
            repository_id=repo.id,
            borg_id="id0",
            name="n0",
            series="default",
            start=datetime(2026, 9, 1),
        )
    )
    db.commit()
    scopes = []

    async def fake_serialized(repository_id, func, scope=None):
        scopes.append(scope)
        return await func()

    async def fake_info(repository, archive_name, **kwargs):
        return {"success": True, "stdout": "{}"}

    monkeypatch.setattr(
        index_exec, "run_serialized_repository_command", fake_serialized
    )
    monkeypatch.setattr("app.core.borg.borg.info_archive", fake_info)
    rows = db.query(Archive).all()
    await index_exec.fill_archive_info(db, repo, rows, {}, limit=5)
    assert scopes == ["metadata"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_refreshes_agent_repository_through_the_agent(
    db, repo, monkeypatch
):
    """The retired stats refresh loop covered agent repositories; the runner
    must too, or their size and encryption never refresh again."""
    repo.executor_type = "agent"
    db.commit()
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )

    async def fake_update(repository, session, **kwargs):
        assert kwargs == {"raise_busy": True}
        repository.total_size = "5.0 GB"
        session.commit()
        return True

    monkeypatch.setattr(
        "app.api.repositories._update_agent_repository_stats", fake_update
    )
    with patch.object(index_exec, "_publish_mqtt_state"):
        outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.status == "completed"
    assert outcome.result["total_size"] == "5.0 GB"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_fails_when_agent_refresh_fails(db, repo, monkeypatch):
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )

    async def fake_update(repository, session, **kwargs):
        assert kwargs == {"raise_busy": True}
        return False

    monkeypatch.setattr(
        "app.api.repositories._update_agent_repository_stats", fake_update
    )
    outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.status == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_lets_the_repository_busy_refusal_reach_the_runner(
    db, repo, monkeypatch
):
    """The admission's 409 is not a failure of the refresh: the runner defers
    the operation on it, so the executor must not turn it into a verdict."""
    from fastapi import HTTPException

    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    refusal = HTTPException(
        status_code=409,
        detail={"key": "backend.errors.jobs.repositoryOperationActive"},
    )

    async def fake_update(repository, session, **kwargs):
        assert kwargs["raise_busy"] is True
        raise refusal

    monkeypatch.setattr(
        "app.api.repositories._update_agent_repository_stats", fake_update
    )
    with pytest.raises(HTTPException) as raised:
        await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert raised.value is refusal


@pytest.mark.unit
def test_registry_has_index_kinds():
    from app.services.operations import executors
    import app.services.operations.executors.index  # noqa: F401  (registers on import)

    assert {"stats", "archive_sync"} <= executors.registered_kinds()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_index_executors_publish_mqtt_state_after_writing_stats(
    db, repo, monkeypatch
):
    """The retired stats refresh loop published Home Assistant state after
    each refresh; the executors that now write those columns keep doing it."""
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(True, [BORG1_ENTRY], "UTC")),
    )
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=0))
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    reasons = []
    with patch(
        "app.services.mqtt_service.mqtt_service.sync_state_with_db",
        side_effect=lambda session, reason="manual": reasons.append(reason),
    ):
        await index_exec.run_archive_sync(_ctx(db, repo))
        monkeypatch.setattr(
            index_exec,
            "measure_repository_size",
            AsyncMock(return_value=SizeResult(bytes=2048, source="borg1_cache_stats")),
        )
        await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert len(reasons) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mqtt_failure_does_not_fail_operation(db, repo, monkeypatch):
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(True, [BORG1_ENTRY], "UTC")),
    )
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=0))
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    with patch(
        "app.services.mqtt_service.mqtt_service.sync_state_with_db",
        side_effect=RuntimeError("broker down"),
    ):
        outcome = await index_exec.run_archive_sync(_ctx(db, repo))
    assert outcome.status == "completed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_raises_the_real_refusal_and_writes_nothing(
    db, repo, monkeypatch
):
    """Composition: the list's refusal comes out of the real helper, through
    run_stats, with the repository row untouched, so the runner's deferral
    retries a refresh that has not half-happened."""
    from fastapi import HTTPException

    repo.executor_type = "agent"
    repo.archive_count = 7
    repo.total_size = "3.0 GB"
    db.commit()
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    refusal = HTTPException(
        status_code=409,
        detail={"key": "backend.errors.jobs.repositoryOperationActive"},
    )

    def queue(session, repository, **kwargs):
        raise refusal

    with (
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=queue,
        ),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
        pytest.raises(HTTPException) as raised,
    ):
        await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert raised.value is refusal
    db.refresh(repo)
    assert (repo.archive_count, repo.total_size) == (7, "3.0 GB")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_keeps_a_later_refusal_and_the_listing(db, repo, monkeypatch):
    """The refusal lands on repo-info, after the agent paid for the listing:
    not raised, since a deferral would repeat the listing; the count is
    written and only the size is left as it was."""
    from fastapi import HTTPException

    repo.executor_type = "agent"
    repo.archive_count = 7
    repo.total_size = "3.0 GB"
    db.commit()
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    refusal = HTTPException(
        status_code=409,
        detail={"key": "backend.errors.jobs.repositoryOperationActive"},
    )

    def queue(session, repository, **kwargs):
        if kwargs["job_kind"] == "repository.rinfo":
            raise refusal
        return SimpleNamespace(id=1)

    listing = json.dumps(
        [
            {"name": "a1", "time": "2026-09-01T01:00:00"},
            {"name": "a2", "time": "2026-09-02T01:00:00"},
        ]
    )
    with (
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=queue,
        ),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
        patch(
            "app.services.repository_executor.wait_for_agent_repository_operation_job",
            new=AsyncMock(return_value={"return_code": 0, "stdout": listing}),
        ),
        patch.object(index_exec, "_publish_mqtt_state"),
    ):
        outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.status == "completed"
    db.refresh(repo)
    assert (repo.archive_count, repo.total_size) == (2, "3.0 GB")


def _agent_for(db, repo, *capabilities):
    from app.core.security import get_password_hash
    from app.database.models import AgentMachine

    agent = AgentMachine(
        name="m",
        agent_id="agt_index",
        token_hash=get_password_hash("t"),
        token_prefix="t",
        status="online",
        capabilities=list(capabilities),
    )
    db.add(agent)
    db.commit()
    repo.executor_type = "agent"
    repo.execution_target = "agent"
    repo.agent_machine_id = agent.id
    db.commit()
    return agent


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("taken", [False, True])
async def test_agent_listing_abandons_only_a_job_no_agent_took(
    db, repo, monkeypatch, taken
):
    """A queued list job nobody waits for is the duplicate every later list
    (stats, the next sync) is refused for, so the sync cancels it before it
    reports the timeout. A job the agent claimed is left to the agent, or
    to the reaper if the agent is gone."""
    from fastapi import HTTPException

    from app.database.models import AgentJob
    from app.services.job_admission import ensure_repository_admission

    _agent_for(db, repo, "repository.list_archives")
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)

    async def fake_wait(db_, job_id, **kwargs):
        if taken:
            job = db_.get(AgentJob, job_id)
            job.status = "claimed"
            db_.commit()
        raise HTTPException(status_code=504, detail="timed out")

    monkeypatch.setattr(
        "app.services.repository_executor.wait_for_agent_repository_operation_job",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
        AsyncMock(return_value=True),
    )
    with pytest.raises(HTTPException) as raised:
        await index_exec.list_archives_for_repository(db, repo, {})
    assert raised.value.status_code == 504
    db.expire_all()
    job = db.query(AgentJob).one()
    if taken:
        assert job.status == "claimed"
        with pytest.raises(HTTPException):
            ensure_repository_admission(db, repo, "repository.list_archives")
    else:
        assert job.status == "canceled"
        ensure_repository_admission(db, repo, "repository.list_archives")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_listing_reports_the_timeout_when_the_cancel_fails(
    db, repo, monkeypatch
):
    """The cancel's own database failure is rolled back and logged, not
    raised: the caller leaves with the timeout it came with, the job stays
    queued, and the session is usable for the runner's own verdict."""
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError

    from app.database.models import AgentJob

    _agent_for(db, repo, "repository.list_archives")
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)

    async def fake_wait(db_, job_id, **kwargs):
        raise HTTPException(status_code=504, detail="timed out")

    monkeypatch.setattr(
        "app.services.repository_executor.wait_for_agent_repository_operation_job",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
        AsyncMock(return_value=True),
    )
    engine = db.get_bind()

    def locked(conn, cursor, statement, parameters, context, executemany):
        # the cancel's UPDATE hits a locked database at the DBAPI layer
        if statement.lstrip().upper().startswith("UPDATE AGENT_JOBS"):
            raise OperationalError(
                statement, parameters, Exception("database is locked")
            )

    event.listen(engine, "before_cursor_execute", locked)
    try:
        with pytest.raises(HTTPException) as raised:
            await index_exec.list_archives_for_repository(db, repo, {})
    finally:
        event.remove(engine, "before_cursor_execute", locked)
    assert raised.value.status_code == 504
    db.expire_all()
    assert db.query(AgentJob).one().status == "queued"
    # the session is usable: the runner writes its verdict through it next
    repo.total_size = "1.0 GB"
    db.commit()
    db.expire_all()
    assert db.get(type(repo), repo.id).total_size == "1.0 GB"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("index_result", [None, (0, 0), (2048, 3)])
async def test_run_stats_persists_an_empty_borg2_index_but_not_failed_measurement(
    db, repo, monkeypatch, index_result
):
    from app.core.borg2 import borg2
    from app.services import storage_usage

    repo.borg_version = 2
    repo.total_size = "42.00 B"
    repo.total_size_bytes = 42
    repo.total_size_source = "compact_stats"
    previous_measurement = datetime(2026, 1, 1)
    repo.total_size_measured_at = previous_measurement
    db.commit()
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(borg2, "rinfo", AsyncMock(return_value={"success": False}))
    monkeypatch.setattr(
        storage_usage, "borg2_index_size", AsyncMock(return_value=index_result)
    )
    monkeypatch.setattr(storage_usage, "storage_used", AsyncMock(return_value=None))

    outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    db.expire_all()

    assert outcome.status == "completed"
    if index_result is None:
        assert outcome.result["bytes"] is None
        assert repo.total_size_bytes == 42
        assert repo.total_size_measured_at == previous_measurement
        assert repo.total_size_source == "compact_stats"
    else:
        assert outcome.result["bytes"] == index_result[0]
        assert outcome.result["source"] == "borg2_index"
        assert repo.total_size_bytes == index_result[0]
        assert repo.total_size_source == "borg2_index"
        assert repo.total_size_measured_at > previous_measurement
        assert repo.total_size == ("0.00 B" if index_result[0] == 0 else "2.00 KB")
