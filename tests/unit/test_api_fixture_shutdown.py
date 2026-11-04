"""Real TestClient cleanup must release fixture locks before draining services."""

import asyncio
from threading import Event

import pytest
from sqlalchemy.orm import Session

from app.database.models import OperationsRunnerLease, Repository
from tests.fixtures.api import test_client as client_fixture


@pytest.mark.parametrize("body_raises", [False, True])
def test_client_cleanup_releases_pending_writes_before_real_shutdown(
    test_db, body_raises
):
    """A pending fixture write must not strand the runner lease at shutdown."""
    from app.main import app

    assert test_db.query(Repository).count() == 0
    committed = Repository(name="committed", path="/tmp/committed", encryption="none")
    test_db.add(committed)
    test_db.commit()
    fixture = client_fixture.__wrapped__(test_db)
    client = next(fixture)
    background_tasks = list(app.state.background_tasks)
    cleaned_up = Event()

    async def start_cleanup_task():
        async def pending_work():
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned_up.set()

        task = asyncio.create_task(pending_work())
        app.state.background_tasks.append(task)
        await asyncio.sleep(0)
        return task

    cleanup_task = client.portal.call(start_cleanup_task)
    try:
        lease = test_db.get(OperationsRunnerLease, 1)
        assert lease.holder is not None
        test_db.add(
            Repository(name="uncommitted", path="/tmp/uncommitted", encryption="none")
        )
        test_db.flush()  # SQLite's write lock remains until rollback/commit.
        if body_raises:
            with pytest.raises(RuntimeError, match="test body failed"):
                fixture.throw(RuntimeError("test body failed"))
        else:
            fixture.close()
        with Session(bind=test_db.bind) as observer:
            assert observer.get(OperationsRunnerLease, 1).holder is None
            assert [repo.name for repo in observer.query(Repository)] == ["committed"]
        assert cleaned_up.is_set()
        assert cleanup_task.done()
        assert all(task.done() for task in background_tasks)
    finally:
        fixture.close()
