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
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    with patch(
        "app.core.borg_router.BorgRouter.calculate_total_size_bytes",
        new=AsyncMock(return_value=2048),
    ):
        outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.result == {"unique_csize": 2048}
    db.refresh(repo)
    assert repo.total_size == "2.00 KB"


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

    async def fake_update(repository, session):
        return True

    monkeypatch.setattr(
        "app.api.repositories._update_agent_repository_stats", fake_update
    )
    with patch.object(index_exec, "_publish_mqtt_state"):
        outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.result == {"total_size": "keep", "source": "agent"}
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

    async def fake_update(repository, session):
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

    async def fake_update(repository, session):
        return False

    monkeypatch.setattr(
        "app.api.repositories._update_agent_repository_stats", fake_update
    )
    outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.status == "failed"


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
        with patch(
            "app.core.borg_router.BorgRouter.calculate_total_size_bytes",
            new=AsyncMock(return_value=2048),
        ):
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
