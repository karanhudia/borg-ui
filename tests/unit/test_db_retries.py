from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.utils.db_retries import commit_with_retry


class FakeDb:
    def __init__(self, dialect_name, side_effects):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self._side_effects = list(side_effects)
        self.rollback_calls = 0

    def commit(self):
        effect = self._side_effects.pop(0)
        if effect is not None:
            raise effect

    def rollback(self):
        self.rollback_calls += 1


def _sqlite_locked_error():
    return OperationalError(
        "UPDATE check_jobs SET status='running'",
        {},
        Exception("database is locked"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_with_retry_retries_sqlite_lock():
    db = FakeDb("sqlite", [_sqlite_locked_error(), None])

    await commit_with_retry(db, retries=2, base_delay_seconds=0)

    assert db.rollback_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_with_retry_does_not_retry_non_sqlite_lock():
    db = FakeDb("postgresql", [_sqlite_locked_error()])

    with pytest.raises(OperationalError):
        await commit_with_retry(db, retries=2, base_delay_seconds=0)

    assert db.rollback_calls == 1
