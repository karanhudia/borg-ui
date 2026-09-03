import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, SystemSettings
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
    assert db.query(SystemSettings).first().last_stats_refresh is not None


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
    reconcile.enqueue_reconcile_runs(db)
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id)
        .order_by(Operation.id)
    ]
    assert kinds == ["archive_sync", "history_merge", "history_index", "stats"]


@pytest.mark.unit
def test_enqueue_reconcile_runs_noop_without_executors(db, repos, monkeypatch):
    monkeypatch.setattr(reconcile, "registered_kinds", lambda: set())
    assert reconcile.enqueue_reconcile_runs(db) == 0
    assert db.query(Operation).count() == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_disabled_when_interval_zero(db, repos, monkeypatch):
    settings = db.query(SystemSettings).first()
    settings.stats_refresh_interval_minutes = 0
    db.commit()
    monkeypatch.setattr(reconcile, "SessionLocal", lambda: db)
    scheduler = reconcile.ReconcileScheduler()
    await scheduler.start()
    assert scheduler.running is False
    assert db.query(Operation).count() == 0
