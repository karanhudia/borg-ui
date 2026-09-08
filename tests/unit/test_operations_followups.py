import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, SystemSettings
from app.services.operations.enqueue import enqueue
from app.services.operations.executors import load_default_executors
from app.services.operations.followups import (
    FOLLOWUPS,
    chain_for,
    enqueue_backup_followups,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repo(db):
    load_default_executors()
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


@pytest.mark.unit
def test_chain_table_matches_spec_7_4():
    assert FOLLOWUPS == {
        "import_connect": ("stats", "archive_sync", "history_index"),
        "backup": ("archive_sync", "history_merge", "history_index", "stats"),
        "prune": ("archive_sync", "history_merge", "stats"),
        "delete_archive": ("archive_sync", "history_merge", "stats"),
        "compact": ("stats",),
        "check": (),
        "wipe": ("archive_sync", "history_merge", "stats"),
        "restore": (),
        "restore_check": (),
        "rclone_sync": (),
        "package_install": (),
        "stats": (),
        "archive_sync": (),
        "history_index": (),
        "history_merge": (),
    }


@pytest.mark.unit
def test_chain_for_filters_to_available_executors():
    assert chain_for("import_connect") == ["stats", "archive_sync", "history_index"]
    assert chain_for("import_connect", available={"stats", "archive_sync"}) == [
        "stats",
        "archive_sync",
    ]
    assert chain_for("prune", available={"stats", "archive_sync"}) == [
        "archive_sync",
        "stats",
    ]
    assert chain_for("check") == []


@pytest.mark.unit
def test_chain_for_rejects_unknown_kind():
    with pytest.raises(ValueError):
        chain_for("bogus")


@pytest.mark.unit
def test_chain_for_drops_history_kinds_for_community():
    from app.services.operations.followups import HISTORY_KINDS

    assert HISTORY_KINDS == {"history_index", "history_merge"}
    assert chain_for("backup", history=False) == [
        "archive_sync",
        "history_merge",
        "stats",
    ]
    assert chain_for("import_connect", history=False) == ["stats", "archive_sync"]
    assert chain_for("backup", history=True) == [
        "archive_sync",
        "history_merge",
        "history_index",
        "stats",
    ]
    assert chain_for(
        "backup", available={"archive_sync", "history_index"}, history=False
    ) == ["archive_sync"]


@pytest.mark.unit
def test_history_enabled_follows_plan(db_session):
    from app.database.models import LicensingState
    from app.services.operations.followups import history_enabled

    assert history_enabled(db_session) is False
    # get_or_create_licensing_state creates the single row on first access
    # above, so flip that row's plan rather than inserting a second one
    # (LicensingState lookups always take the first row in the table).
    state = db_session.query(LicensingState).first()
    state.plan = "pro"
    state.status = "active"
    db_session.commit()
    assert history_enabled(db_session) is True


@pytest.mark.unit
def test_community_keeps_history_merge_so_removed_archives_are_deleted():
    """history_merge is the only place an Archive row is deleted, so dropping
    it on Community would leave every pruned archive in the table forever.
    Only history_index is plan gated (spec 11.2)."""
    from app.services.operations.followups import PLAN_GATED_KINDS

    assert PLAN_GATED_KINDS == {"history_index"}
    assert chain_for("prune", history=False) == [
        "archive_sync",
        "history_merge",
        "stats",
    ]
    assert chain_for("delete_archive", history=False) == [
        "archive_sync",
        "history_merge",
        "stats",
    ]
    assert chain_for("wipe", history=False) == [
        "archive_sync",
        "history_merge",
        "stats",
    ]


@pytest.mark.unit
def test_enqueue_backup_followups_creates_the_backup_chain(db, repo, monkeypatch):
    """A backup that completed outside the runner (#933) enqueues the spec
    7.4 chain as a follow-up run; history_index is dropped without a plan."""
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    ops = enqueue_backup_followups(
        db, repo.id, scheduled_job_id=None, backup_plan_run_id=None
    )
    assert [o.kind for o in ops] == ["archive_sync", "history_merge", "stats"]
    assert {o.trigger for o in ops} == {"followup"}
    assert {o.priority for o in ops} == {10}
    assert ops[1].depends_on_id == ops[0].id
    assert len({o.run_id for o in ops}) == 1


@pytest.mark.unit
def test_enqueue_backup_followups_skips_when_an_index_run_is_queued(
    db, repo, monkeypatch
):
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    assert enqueue_backup_followups(db, repo.id) == []


@pytest.mark.unit
def test_enqueue_backup_followups_ignores_a_running_index_run(db, repo, monkeypatch):
    """A running listing may predate the backup, so it does not satisfy it."""
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    running = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    running.status = "running"
    db.commit()
    ops = enqueue_backup_followups(db, repo.id, commit=False)
    db.commit()
    assert [o.kind for o in ops] == ["archive_sync", "history_merge", "stats"]
    assert db.query(Operation).filter_by(status="queued").count() == 3


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["stats", "history_index", "history_merge"])
def test_queued_non_listing_work_does_not_suppress_backup_followups(
    db, repo, monkeypatch, kind
):
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    enqueue(db, kind, repository_id=repo.id, trigger="reconcile")
    ops = enqueue_backup_followups(db, repo.id)
    assert any(op.kind == "archive_sync" for op in ops)


@pytest.mark.unit
def test_running_listing_with_queued_children_does_not_suppress_followups(
    db, repo, monkeypatch
):
    from app.services.operations.enqueue import enqueue_chain

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    chain = enqueue_chain(
        db,
        ["archive_sync", "history_merge", "stats"],
        repository_id=repo.id,
        trigger="reconcile",
    )
    chain[0].status = "running"
    db.commit()
    ops = enqueue_backup_followups(db, repo.id)
    assert any(op.kind == "archive_sync" for op in ops)


@pytest.mark.unit
@pytest.mark.parametrize(
    "parent_status,skip_reason,suppresses",
    [
        ("completed", None, True),
        ("completed_with_warnings", None, True),
        ("skipped", "agent_diff_unsupported", True),
        ("skipped", "plan_locked", True),
        ("skipped", None, True),
        ("skipped", "dependency_failed", False),
        ("failed", None, False),
        ("cancelled", None, False),
        ("running", None, False),
        ("queued", None, False),
        ("missing", None, False),
    ],
)
def test_only_listing_with_satisfied_parent_suppresses_followups(
    db, repo, monkeypatch, parent_status, skip_reason, suppresses
):
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    parent = enqueue(db, "stats", repository_id=repo.id, trigger="manual")
    listing = enqueue(
        db,
        "archive_sync",
        repository_id=repo.id,
        depends_on_id=parent.id,
        trigger="manual",
    )
    if parent_status == "missing":
        # Model a missing dependency defensively (foreign keys are disabled here).
        listing.depends_on_id = parent.id + 1000
    else:
        parent.status = parent_status
        parent.skip_reason = skip_reason
    db.commit()
    ops = enqueue_backup_followups(db, repo.id)
    assert bool(ops) is not suppresses
    if ops:
        assert ops[0].kind == "archive_sync"


@pytest.mark.unit
def test_listing_behind_queued_parent_with_failed_ancestor_does_not_suppress(
    db, repo, monkeypatch
):
    from app.services.operations.enqueue import enqueue_chain

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    chain = enqueue_chain(
        db,
        ["stats", "history_index", "archive_sync"],
        repository_id=repo.id,
        trigger="manual",
    )
    chain[0].status = "failed"
    db.commit()
    ops = enqueue_backup_followups(db, repo.id)
    assert ops and ops[0].kind == "archive_sync"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("plan", ["community", "pro"])
async def test_backup_followup_chain_deletes_removed_archive_and_keeps_survivor(
    db, repo, monkeypatch, tmp_path, plan
):
    import asyncio
    from datetime import datetime
    from unittest.mock import AsyncMock

    from app.core.borg_router import BorgRouter
    from app.database.models import Archive, LicensingState
    from app.services.operations.executors import index, history
    from app.services.operations.runner import OperationRunner
    from app.services.storage_usage import SizeResult

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.config.settings.index_archive_info_per_run", 0)
    db.add(LicensingState(instance_id="followup-test", plan=plan, status="active"))
    survivor = Archive(
        repository_id=repo.id,
        borg_id="aa11",
        name="nas-2026-09-01",
        series="nas",
        start=datetime(2026, 9, 1),
        history_state="indexed",
    )
    removed = Archive(
        repository_id=repo.id,
        borg_id="bb22",
        name="nas-2026-09-02",
        series="nas",
        start=datetime(2026, 9, 2),
    )
    db.add_all([survivor, removed])
    repo.archive_count = 2
    repo.last_backup = removed.start
    db.commit()
    survivor_id, removed_id = survivor.id, removed.id
    monkeypatch.setattr(
        BorgRouter,
        "list_archives_checked",
        AsyncMock(
            return_value=(
                True,
                [
                    {
                        "id": "aa11",
                        "name": "nas-2026-09-01",
                        "time": "2026-09-01T00:00:00.000000",
                    }
                ],
            )
        ),
    )
    monkeypatch.setattr(
        index, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(
        index,
        "measure_repository_size",
        AsyncMock(return_value=SizeResult(bytes=123, source="borg1_cache_stats")),
    )
    runner = OperationRunner(
        session_factory=sessionmaker(bind=db.get_bind()),
        registry={
            "archive_sync": index.run_archive_sync,
            "history_merge": history.run_history_merge,
            "history_index": history.run_history_index,
            "stats": index.run_stats,
        },
    )
    ops = enqueue_backup_followups(db, repo.id)
    for _ in range(10):
        await runner.tick()
        if runner.running_tasks:
            await asyncio.gather(*list(runner.running_tasks.values()))
    db.expire_all()
    assert db.get(Archive, removed_id) is None
    assert db.get(Archive, survivor_id).borg_id == "aa11"
    assert db.query(Archive).filter_by(repository_id=repo.id).count() == 1
    assert repo.archive_count == 1
    assert repo.last_backup == datetime(2026, 9, 1)
    assert all(db.get(Operation, op.id).status == "completed" for op in ops)
