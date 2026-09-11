"""The follow-up chain and the reconcile tick honour the index mode
(spec section 6.8)."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, SystemSettings
from app.services.operations import reconcile
from app.services.operations.followups import chain_for, chain_for_repository


ALL_KINDS = {"stats", "archive_sync", "history_index", "history_merge"}


@pytest.fixture(autouse=True)
def _executors(monkeypatch):
    """No executors are registered in a bare unit environment, and an
    unregistered kind is dropped before the mode ever sees it."""
    monkeypatch.setattr(reconcile, "registered_kinds", lambda: ALL_KINDS)
    monkeypatch.setattr(
        "app.services.operations.executors.registered_kinds", lambda: ALL_KINDS
    )


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
        engine.dispose()


def _repository(db, mode, name=None):
    name = name or f"repo-{mode}"
    repo = Repository(name=name, path=f"/tmp/{name}", index_mode=mode)
    db.add(repo)
    if db.query(SystemSettings).first() is None:
        db.add(SystemSettings())
    db.commit()
    return repo


def test_chain_for_full_is_unchanged():
    assert chain_for("backup") == [
        "archive_sync",
        "history_merge",
        "history_index",
        "stats",
    ]


def test_chain_for_archives_keeps_the_listing_and_the_size():
    assert chain_for("backup", mode="archives") == ["archive_sync", "stats"]


def test_chain_for_off_is_empty():
    assert chain_for("backup", mode="off") == []


def test_chain_for_repository_reads_the_repository_mode(db):
    repo = _repository(db, "archives")
    assert chain_for_repository(db, "backup", repo.id, history=True) == [
        "archive_sync",
        "stats",
    ]


def test_chain_for_repository_with_no_repository_is_the_default(db):
    # Work with no repository (a package install) is not index work: it has
    # no chain of its own and no mode to read.
    _repository(db, "off")
    assert chain_for_repository(db, "package_install", None, history=True) == []


def test_reconcile_kinds_drop_history_in_archives_mode(db):
    kinds = reconcile.reconcile_kinds(db, history=True, mode="archives")
    assert "history_index" not in kinds
    assert "history_merge" not in kinds
    assert "archive_sync" in kinds


def test_reconcile_kinds_are_empty_for_off(db):
    assert reconcile.reconcile_kinds(db, history=True, mode="off") == []


def test_the_reconcile_tick_enqueues_nothing_for_an_off_repository(db):
    repo = _repository(db, "off")
    assert reconcile.enqueue_reconcile_run(db, repo.id, history=True) == []
    assert db.query(Operation).count() == 0


def test_a_manual_run_still_lists_an_off_repository(db):
    # Spec 6.8: manual work is not gated by the mode, it just does not repeat.
    repo = _repository(db, "off")
    ops = reconcile.enqueue_reconcile_run(db, repo.id, history=True, manual=True)
    assert [op.kind for op in ops] == ["archive_sync", "stats"]


def test_a_manual_run_never_re_enables_history(db):
    repo = _repository(db, "archives")
    ops = reconcile.enqueue_reconcile_run(db, repo.id, history=True, manual=True)
    assert [op.kind for op in ops] == ["archive_sync", "stats"]


def test_the_reconcile_sweep_skips_off_repositories(db):
    _repository(db, "off")
    full = _repository(db, "full")
    assert reconcile.enqueue_reconcile_runs(db, history=True) == 1
    assert {op.repository_id for op in db.query(Operation).all()} == {full.id}
