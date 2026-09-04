import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    LicensingState,
    Operation,
    Repository,
    SystemSettings,
)
from app.services.operations import reconcile
from app.services.operations.enqueue import enqueue


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
def repos(db):
    a = Repository(name="a", path="/tmp/a", encryption="none", compression="lz4")
    b = Repository(name="b", path="/tmp/b", encryption="none", compression="lz4")
    db.add_all([a, b, SystemSettings()])
    db.commit()
    return a, b


@pytest.mark.unit
def test_enqueue_reconcile_runs_skips_repos_with_active_index_work(
    db, repos, monkeypatch
):
    monkeypatch.setattr(
        reconcile, "registered_kinds", lambda: {"stats", "archive_sync"}
    )
    a, b = repos
    enqueue(db, "stats", repository_id=a.id)  # queued index work on a
    count = reconcile.enqueue_reconcile_runs(db)
    assert count == 1
    rows = (
        db.query(Operation)
        .filter(Operation.repository_id == b.id)
        .order_by(Operation.id)
        .all()
    )
    assert [r.kind for r in rows] == ["archive_sync", "stats"]
    assert all(r.trigger == "reconcile" and r.priority == 20 for r in rows)
    assert rows[1].depends_on_id == rows[0].id
    # last_stats_refresh is a completion signal, set by the stats executor
    # once it actually finishes, not when the reconcile chain is enqueued.
    assert db.query(SystemSettings).first().last_stats_refresh is None


@pytest.mark.unit
def test_enqueue_reconcile_runs_includes_history_kinds_when_registered(
    db, repos, monkeypatch
):
    monkeypatch.setattr(
        reconcile,
        "registered_kinds",
        lambda: {"stats", "archive_sync", "history_merge", "history_index"},
    )
    a, _ = repos
    reconcile.enqueue_reconcile_runs(db, history=True)
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id)
        .order_by(Operation.id)
    ]
    assert kinds == ["archive_sync", "history_merge", "history_index", "stats"]


@pytest.mark.unit
def test_enqueue_reconcile_runs_omits_history_kinds_for_community(
    db, repos, monkeypatch
):
    monkeypatch.setattr(
        reconcile,
        "registered_kinds",
        lambda: {"stats", "archive_sync", "history_merge", "history_index"},
    )
    a, _ = repos
    reconcile.enqueue_reconcile_runs(db, history=False)
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id)
        .order_by(Operation.id)
    ]
    # history_merge stays: it is what deletes rows for archives that are gone,
    # which Community installs need just as much as Pro ones.
    assert kinds == ["archive_sync", "history_merge", "stats"]


@pytest.mark.unit
def test_enqueue_reconcile_runs_asks_the_plan_when_history_is_none(
    db, repos, monkeypatch
):
    monkeypatch.setattr(
        reconcile,
        "registered_kinds",
        lambda: {"stats", "archive_sync", "history_merge", "history_index"},
    )
    a, _ = repos
    reconcile.enqueue_reconcile_runs(db)
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id)
        .order_by(Operation.id)
    ]
    assert kinds == ["archive_sync", "history_merge", "stats"]
    for op in db.query(Operation).filter(Operation.repository_id == a.id):
        op.status = "completed"
    db.commit()

    # get_or_create_licensing_state created the single row above; flip its
    # plan rather than inserting a second one (lookups always take the
    # first row in the table).
    state = db.query(LicensingState).first()
    if state is None:
        db.add(LicensingState(instance_id="t-reconcile", plan="pro", status="active"))
    else:
        state.plan = "pro"
        state.status = "active"
    db.commit()
    reconcile.enqueue_reconcile_runs(db)
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id)
        .order_by(Operation.id)
    ]
    assert kinds == [
        "archive_sync",
        "history_merge",
        "stats",
        "archive_sync",
        "history_merge",
        "history_index",
        "stats",
    ]


@pytest.mark.unit
def test_bootstrap_history_once_runs_a_single_time(db, repos):
    with patch(
        "app.services.operations.reconcile.enqueue_reconcile_runs", return_value=1
    ) as enq:
        assert reconcile.bootstrap_history_once(db) == 1
        assert reconcile.bootstrap_history_once(db) == 0
    assert enq.call_count == 1
    assert db.query(SystemSettings).first().history_bootstrap_at is not None


@pytest.mark.unit
def test_enqueue_reconcile_runs_noop_without_executors(db, repos, monkeypatch):
    monkeypatch.setattr(reconcile, "registered_kinds", lambda: set())
    assert reconcile.enqueue_reconcile_runs(db) == 0
    assert db.query(Operation).count() == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_stays_alive_when_interval_zero(db, repos, monkeypatch):
    settings = db.query(SystemSettings).first()
    settings.stats_refresh_interval_minutes = 0
    db.commit()
    monkeypatch.setattr(reconcile, "SessionLocal", lambda: db)
    monkeypatch.setattr(reconcile, "POLL_INTERVAL_WHEN_DISABLED_MINUTES", 0)
    scheduler = reconcile.ReconcileScheduler()
    task = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0.05)
    assert scheduler.running is True
    assert db.query(Operation).count() == 0
    scheduler.stop()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.unit
def test_scheduler_reads_interval_live_each_poll(db, repos, monkeypatch):
    """The scheduler re-reads stats_refresh_interval_minutes from settings on
    every poll rather than caching it once at start(), so raising it above 0
    later resumes reconciliation without another start() call."""
    settings = db.query(SystemSettings).first()
    settings.stats_refresh_interval_minutes = 0
    db.commit()
    monkeypatch.setattr(reconcile, "SessionLocal", lambda: db)
    scheduler = reconcile.ReconcileScheduler()
    assert scheduler._interval_minutes() == 0

    # _interval_minutes() closes its (test-shared) session each call, which
    # detaches `settings` from it - re-fetch before mutating again.
    settings = db.query(SystemSettings).first()
    settings.stats_refresh_interval_minutes = 30
    db.commit()
    assert scheduler._interval_minutes() == 30


@pytest.mark.unit
def test_bootstrap_claims_the_flag_before_enqueueing(db, repos, monkeypatch):
    """Two processes starting at once both read a null history_bootstrap_at and
    would each enqueue a full set of chains. The claim has to be committed
    before the enqueue, so the second caller sees it and stops."""
    seen: list[int] = []

    def enqueue(session):
        # What a concurrent starter observes at this point in the first call.
        other = session.query(SystemSettings).first()
        seen.append(0 if other.history_bootstrap_at is None else 1)
        return 3

    monkeypatch.setattr(reconcile, "enqueue_reconcile_runs", enqueue)
    assert reconcile.bootstrap_history_once(db) == 3
    assert seen == [1]
    assert reconcile.bootstrap_history_once(db) == 0


@pytest.mark.unit
def test_a_failed_bootstrap_releases_its_claim(db, repos, monkeypatch):
    """Otherwise the bootstrap is recorded as done and never runs again."""

    def boom(session):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(reconcile, "enqueue_reconcile_runs", boom)
    with pytest.raises(RuntimeError):
        reconcile.bootstrap_history_once(db)

    assert db.query(SystemSettings).first().history_bootstrap_at is None
