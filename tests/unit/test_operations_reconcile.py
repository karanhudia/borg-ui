import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
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
def test_enqueue_reconcile_run_can_be_forced_past_active_index_work(
    db, repos, monkeypatch
):
    """A caller whose run the in-flight work cannot replace (the mode
    catch-up, the reopen after an executor change) queues anyway; the
    runner's admission serialises the two on the repository."""
    monkeypatch.setattr(
        reconcile, "registered_kinds", lambda: {"stats", "archive_sync"}
    )
    a, _ = repos
    syncing = enqueue(db, "archive_sync", repository_id=a.id)
    syncing.status = "running"
    enqueue(db, "stats", repository_id=a.id, depends_on_id=syncing.id)
    db.commit()

    assert reconcile.enqueue_reconcile_run(db, a.id) == []

    rows = reconcile.enqueue_reconcile_run(db, a.id, force=True)
    assert [r.kind for r in rows] == ["archive_sync", "stats"]
    assert rows[0].depends_on_id is None
    assert rows[1].depends_on_id == rows[0].id
    assert all(r.trigger == "reconcile" and r.status == "queued" for r in rows)


@pytest.mark.unit
def test_enqueue_reconcile_runs_despite_a_running_history_index(db, repos, monkeypatch):
    """A history index can run for hours. It must not block the hourly
    archive sync, or the repository reads as stale while nothing is wrong."""
    monkeypatch.setattr(
        reconcile,
        "registered_kinds",
        lambda: {"stats", "archive_sync", "history_index"},
    )
    a, b = repos
    op = enqueue(db, "history_index", repository_id=a.id)
    op.status = "running"
    db.commit()
    count = reconcile.enqueue_reconcile_runs(db)
    assert count == 2
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id, Operation.trigger == "reconcile")
        .order_by(Operation.id)
        .all()
    ]
    assert kinds == ["archive_sync", "history_index", "stats"]


@pytest.mark.unit
def test_enqueue_reconcile_runs_skips_repos_with_a_running_archive_sync(
    db, repos, monkeypatch
):
    monkeypatch.setattr(
        reconcile, "registered_kinds", lambda: {"stats", "archive_sync"}
    )
    a, b = repos
    op = enqueue(db, "archive_sync", repository_id=a.id)
    op.status = "running"
    db.commit()
    assert reconcile.enqueue_reconcile_runs(db) == 1
    assert (
        db.query(Operation)
        .filter(Operation.repository_id == a.id, Operation.trigger == "reconcile")
        .count()
        == 0
    )


@pytest.mark.unit
def test_enqueue_reconcile_runs_includes_history_kinds_when_registered(
    db, repos, monkeypatch
):
    monkeypatch.setattr(
        reconcile,
        "registered_kinds",
        lambda: {"stats", "archive_sync", "history_index"},
    )
    a, _ = repos
    reconcile.enqueue_reconcile_runs(db)
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id)
        .order_by(Operation.id)
    ]
    assert kinds == ["archive_sync", "history_index", "stats"]


@pytest.mark.unit
def test_enqueue_reconcile_runs_includes_history_kinds_on_community(
    db, repos, monkeypatch
):
    """The index is built on every plan (spec
    2026-09-21-community-teasers-and-feature-trials, section 2). No
    entitlement is active in this database, so this is a Community install."""
    monkeypatch.setattr(
        reconcile,
        "registered_kinds",
        lambda: {"stats", "archive_sync", "history_index"},
    )
    a, _ = repos
    reconcile.enqueue_reconcile_runs(db)
    kinds = [
        r.kind
        for r in db.query(Operation)
        .filter(Operation.repository_id == a.id)
        .order_by(Operation.id)
    ]
    assert kinds == ["archive_sync", "history_index", "stats"]


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


T0 = datetime(2026, 1, 1, 12, 0, 0)


class FakeClock:
    """Stands in for `asyncio.sleep` and `utc_now` inside the reconcile
    module: a sleep moves the clock forward instead of waiting, and every
    reconcile tick is recorded with the time it ran at."""

    def __init__(self, monkeypatch, db, now=T0):
        self.now = now
        self.runs: list[datetime] = []
        self.on_sleep = None
        self._scheduler = None
        self._stop_at = now
        enqueue_runs = reconcile.enqueue_reconcile_runs

        def record(session, **kwargs):
            self.runs.append(self.now)
            if len(self.runs) > 50:  # a loop that never sleeps
                self._scheduler.stop()
            return enqueue_runs(session, **kwargs)

        monkeypatch.setattr(reconcile, "SessionLocal", lambda: db)
        monkeypatch.setattr(reconcile, "utc_now", lambda: self.now)
        monkeypatch.setattr(reconcile, "asyncio", SimpleNamespace(sleep=self.sleep))
        monkeypatch.setattr(reconcile, "enqueue_reconcile_runs", record)

    async def sleep(self, seconds):
        # A process can end in the middle of a sleep.
        self.now = min(self.now + timedelta(seconds=seconds), self._stop_at)
        if self.on_sleep is not None:
            self.on_sleep(self)
        if self.now >= self._stop_at:
            self._scheduler.stop()
        await asyncio.sleep(0)

    async def run_scheduler(self, *, minutes):
        """One process lifetime: a fresh scheduler, stopped after `minutes`."""
        self._scheduler = reconcile.ReconcileScheduler()
        self._stop_at = self.now + timedelta(minutes=minutes)
        await asyncio.wait_for(self._scheduler.start(), timeout=5)


def _set_interval(db, minutes):
    db.query(SystemSettings).first().stats_refresh_interval_minutes = minutes
    db.commit()


def _set_last_tick(db, when):
    db.query(SystemSettings).first().last_reconcile_tick_at = when
    db.commit()


def _last_tick(db):
    db.expire_all()
    return db.query(SystemSettings).first().last_reconcile_tick_at


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_runs_at_once_when_the_last_tick_is_overdue(
    db, repos, monkeypatch
):
    monkeypatch.setattr(
        reconcile, "registered_kinds", lambda: {"stats", "archive_sync"}
    )
    a, b = repos
    # The scheduler closes the (test-shared) session, which detaches a and b.
    repository_ids = {a.id, b.id}
    _set_interval(db, 60)
    _set_last_tick(db, T0 - timedelta(hours=3))
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=30)
    assert clock.runs == [T0]
    queued = db.query(Operation).filter(Operation.status == "queued")
    assert {o.repository_id for o in queued} == repository_ids
    assert _last_tick(db) == T0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_waits_only_the_remainder_after_a_recent_tick(
    db, repos, monkeypatch
):
    _set_interval(db, 60)
    _set_last_tick(db, T0 - timedelta(minutes=45))
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=50)
    assert clock.runs == [T0 + timedelta(minutes=15)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_runs_at_once_without_a_previous_tick(db, repos, monkeypatch):
    _set_interval(db, 60)
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=30)
    assert clock.runs == [T0]
    assert _last_tick(db) == T0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_never_runs_while_disabled(db, repos, monkeypatch):
    """An overdue last tick does not override `interval <= 0`."""
    _set_last_tick(db, T0 - timedelta(days=30))
    for interval in (0, -1):
        _set_interval(db, interval)
        clock = FakeClock(monkeypatch, db)
        await clock.run_scheduler(minutes=7 * 24 * 60)
        assert clock.runs == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_resumes_an_overdue_tick_once_enabled(db, repos, monkeypatch):
    _set_interval(db, 0)
    _set_last_tick(db, T0 - timedelta(days=1))
    clock = FakeClock(monkeypatch, db)
    enable_at = T0 + timedelta(minutes=20)

    def enable(c):
        if c.now == enable_at:
            _set_interval(db, 60)

    clock.on_sleep = enable
    await clock.run_scheduler(minutes=50)
    assert clock.runs == [enable_at]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_applies_an_interval_changed_while_waiting(
    db, repos, monkeypatch
):
    _set_interval(db, 7 * 24 * 60)
    _set_last_tick(db, T0)
    clock = FakeClock(monkeypatch, db)

    def shorten(c):
        if c.now == T0 + timedelta(minutes=30):
            _set_interval(db, 60)

    clock.on_sleep = shorten
    await clock.run_scheduler(minutes=90)
    assert clock.runs == [T0 + timedelta(minutes=60)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restart_mid_interval_keeps_the_next_tick_time(db, repos, monkeypatch):
    _set_interval(db, 60)
    _set_last_tick(db, T0)
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=30)
    assert clock.runs == []
    # The process restarts half way through the interval.
    await clock.run_scheduler(minutes=45)
    assert clock.runs == [T0 + timedelta(minutes=60)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restart_after_a_single_repository_resync_keeps_the_next_tick_time(
    db, repos, monkeypatch
):
    """A resync of one repository is a reconcile run too, but it is not the
    scheduler's tick: the other repositories are still due on time."""
    monkeypatch.setattr(
        reconcile, "registered_kinds", lambda: {"stats", "archive_sync"}
    )
    # The scheduler closes the (test-shared) session, which detaches a.
    repository_id = repos[0].id
    _set_interval(db, 60)
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=55)
    assert clock.runs == [T0]
    db.query(Operation).update({"status": "completed"})
    db.commit()
    assert reconcile.enqueue_reconcile_run(db, repository_id, manual=True)
    # The process restarts right after the resync.
    await clock.run_scheduler(minutes=30)
    assert clock.runs == [T0, T0 + timedelta(minutes=60)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restart_after_a_tick_that_enqueued_nothing_waits_the_remainder(
    db, monkeypatch
):
    db.add(SystemSettings(stats_refresh_interval_minutes=60))
    db.commit()
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=10)
    assert clock.runs == [T0]
    assert db.query(Operation).count() == 0
    await clock.run_scheduler(minutes=120)
    assert clock.runs == [
        T0,
        T0 + timedelta(minutes=60),
        T0 + timedelta(minutes=120),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_survives_an_interval_beyond_the_datetime_range(
    db, repos, monkeypatch
):
    _set_interval(db, 10**10)
    _set_last_tick(db, T0)
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=60)
    assert clock.runs == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_yields_between_ticks_that_outlast_the_interval(
    db, repos, monkeypatch
):
    """A tick that takes longer than the interval leaves the next one due
    at once; the loop must still give way to the event loop in between."""
    _set_interval(db, 1)
    clock = FakeClock(monkeypatch, db)
    enqueue_runs = reconcile.enqueue_reconcile_runs
    events = []
    sleep = clock.sleep

    def slow(session, **kwargs):
        events.append("tick")
        clock.now += timedelta(minutes=2)
        if len(events) >= 5:
            clock._scheduler.stop()
        return enqueue_runs(session, **kwargs)

    async def recording_sleep(seconds):
        events.append("sleep")
        await sleep(seconds)

    monkeypatch.setattr(reconcile, "enqueue_reconcile_runs", slow)
    monkeypatch.setattr(reconcile, "asyncio", SimpleNamespace(sleep=recording_sleep))
    await clock.run_scheduler(minutes=60)
    assert events[:5] == ["tick", "sleep", "tick", "sleep", "tick"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_read_of_the_last_tick_is_retried_not_taken_as_none(
    db, repos, monkeypatch
):
    _set_interval(db, 60)
    _set_last_tick(db, T0 - timedelta(minutes=30))
    clock = FakeClock(monkeypatch, db)
    failures = [RuntimeError("database is locked")]

    def session():
        if failures:
            raise failures.pop()
        return db

    monkeypatch.setattr(reconcile, "SessionLocal", session)
    await clock.run_scheduler(minutes=45)
    assert clock.runs == [T0 + timedelta(minutes=30)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_does_not_create_the_settings_row(db, monkeypatch):
    """The row is created by the settings routes. Without it the interval
    is the default and the tick time is kept in memory only."""
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=90)
    assert clock.runs == [T0, T0 + timedelta(minutes=60)]
    assert db.query(SystemSettings).count() == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_tick_is_not_stored_and_is_repeated_after_a_restart(
    db, repos, monkeypatch
):
    _set_interval(db, 60)
    _set_last_tick(db, T0 - timedelta(hours=2))
    clock = FakeClock(monkeypatch, db)
    enqueue_runs = reconcile.enqueue_reconcile_runs
    failures = [RuntimeError("database is locked")]

    def fail_once(session, **kwargs):
        enqueue_runs(session, **kwargs)  # recorded by the clock
        if failures:
            raise failures.pop()

    monkeypatch.setattr(reconcile, "enqueue_reconcile_runs", fail_once)
    # Within the process a failed tick waits a full interval, as before.
    await clock.run_scheduler(minutes=30)
    assert clock.runs == [T0]
    assert _last_tick(db) == T0 - timedelta(hours=2)
    await clock.run_scheduler(minutes=30)
    assert clock.runs == [T0, T0 + timedelta(minutes=30)]
    assert _last_tick(db) == T0 + timedelta(minutes=30)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_runs_at_once_when_the_last_tick_is_in_the_future(
    db, repos, monkeypatch
):
    """The clock moved back. Waiting for it to catch up could take
    arbitrarily long, so the tick runs and stores a usable time."""
    _set_interval(db, 60)
    _set_last_tick(db, T0 + timedelta(days=1))
    clock = FakeClock(monkeypatch, db)
    await clock.run_scheduler(minutes=90)
    assert clock.runs == [T0, T0 + timedelta(minutes=60)]
    assert _last_tick(db) == T0 + timedelta(minutes=60)


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


@pytest.mark.unit
def test_enqueue_reconcile_run_omits_history_index_for_an_agent_repository(
    db, monkeypatch
):
    """The history stage does not exist for an agent's repository (the
    server cannot diff it), so the reconcile chain never creates it there,
    while a server-side repository on the same install keeps it."""
    monkeypatch.setattr(
        reconcile,
        "registered_kinds",
        lambda: {"archive_sync", "history_index", "stats"},
    )
    server = Repository(name="server", path="/repo/server", borg_version=1)
    agent = Repository(
        name="agent",
        path="/repo/agent",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
    )
    db.add_all([server, agent])
    db.commit()

    kinds_server = [o.kind for o in reconcile.enqueue_reconcile_run(db, server.id)]
    kinds_agent = [o.kind for o in reconcile.enqueue_reconcile_run(db, agent.id)]

    assert kinds_server == ["archive_sync", "history_index", "stats"]
    assert kinds_agent == ["archive_sync", "stats"]
