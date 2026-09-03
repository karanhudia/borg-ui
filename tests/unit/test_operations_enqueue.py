import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.enqueue import enqueue, enqueue_chain, new_run_id


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
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.commit()
    return r


@pytest.mark.unit
def test_enqueue_fills_category_priority_and_run_id(db, repo):
    op = enqueue(db, "stats", repository_id=repo.id, trigger="reconcile")
    assert op.id is not None
    assert op.category == "index"
    assert op.priority == 20
    assert op.status == "queued"
    assert len(op.run_id) == 36
    assert db.query(Operation).count() == 1


@pytest.mark.unit
def test_enqueue_explicit_priority_wins(db, repo):
    op = enqueue(db, "stats", repository_id=repo.id, trigger="reconcile", priority=3)
    assert op.priority == 3


@pytest.mark.unit
def test_enqueue_rejects_unknown_kind_and_trigger(db, repo):
    with pytest.raises(ValueError):
        enqueue(db, "bogus", repository_id=repo.id)
    with pytest.raises(ValueError):
        enqueue(db, "stats", repository_id=repo.id, trigger="cron")


@pytest.mark.unit
def test_enqueue_chain_links_dependencies(db, repo):
    parent = enqueue(db, "import_connect", repository_id=repo.id, trigger="import")
    chain = enqueue_chain(
        db,
        ["stats", "archive_sync"],
        repository_id=repo.id,
        trigger="followup",
        run_id=parent.run_id,
        depends_on_id=parent.id,
    )
    assert [c.kind for c in chain] == ["stats", "archive_sync"]
    assert chain[0].depends_on_id == parent.id
    assert chain[1].depends_on_id == chain[0].id
    assert {c.run_id for c in chain} == {parent.run_id}
    assert all(c.priority == 10 for c in chain)


@pytest.mark.unit
def test_enqueue_wakes_runner(db, repo, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.operations.enqueue.wake_runner", lambda: calls.append(1)
    )
    enqueue(db, "stats", repository_id=repo.id)
    assert calls == [1]


@pytest.mark.unit
def test_new_run_id_is_unique():
    assert new_run_id() != new_run_id()
