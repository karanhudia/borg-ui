"""A refused admission lets go of the write lock it took.

Admission takes the repository scope lock before looking at active work; on
SQLite that is the database write lock. A plan whose backup was refused then
recorded the failure through a session of its own while the refused session
still held that lock, and waited on itself: 4 attempts x the 30s busy timeout,
with the event loop blocked the whole time (two plans started together on one
repository froze the UI). The scheduler, which moves on to its next due job on
the same session, held it across unrelated work.

The shared test engine is one in-memory connection, where no lock can ever
be contended, so these tests build a file database with real connections.
"""

import time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.models import Operation, Repository
from app.services.job_admission import OPERATION_BACKUP, ensure_repository_admission

# Long enough for any real commit, short enough that a held lock fails the
# test in well under a second instead of hanging it.
BUSY_TIMEOUT_MS = 500


@pytest.fixture
def file_sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lock.db'}")

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield factory
    engine.dispose()


def _repository_with_running_backup(factory):
    with factory() as db:
        repo = Repository(
            name="Busy", path="/repos/busy", encryption="none", repository_type="local"
        )
        db.add(repo)
        db.flush()
        db.add(
            Operation(
                repository_id=repo.id,
                kind="backup",
                category="backup",
                status="running",
                trigger="manual",
                run_id="run-running-backup",
            )
        )
        db.commit()
        return repo.id


@pytest.mark.unit
@pytest.mark.parametrize(
    "running_kind",
    ["backup", "prune"],
    ids=["duplicate-operation", "conflicting-write"],
)
def test_refused_admission_does_not_block_another_session(file_sessions, running_kind):
    repo_id = _repository_with_running_backup(file_sessions)
    if running_kind != "backup":
        with file_sessions() as db:
            db.query(Operation).update({"kind": running_kind})
            db.commit()

    refused = file_sessions()
    try:
        repo = refused.get(Repository, repo_id)
        with pytest.raises(HTTPException) as exc:
            ensure_repository_admission(refused, repo, OPERATION_BACKUP)
        assert exc.value.status_code == 409
        assert exc.value.detail["params"]["repository_id"] == repo_id

        # The plan's failure bookkeeping: a write from a different session
        # while the refused one is still open.
        started = time.monotonic()
        with file_sessions() as other:
            other.execute(
                text("UPDATE repositories SET name = 'still writable' WHERE id = :id"),
                {"id": repo_id},
            )
            other.commit()
        assert time.monotonic() - started < BUSY_TIMEOUT_MS / 1000

        # The refused session stays usable for the caller's own bookkeeping.
        refused.get(Repository, repo_id).name = "written by the refused session"
        refused.commit()
    finally:
        refused.close()


@pytest.mark.unit
def test_admission_still_holds_the_lock_when_it_admits(file_sessions):
    # The lock exists to serialize check-then-insert; admitting must keep it
    # until the caller commits the job it is about to queue.
    with file_sessions() as db:
        repo = Repository(
            name="Idle", path="/repos/idle", encryption="none", repository_type="local"
        )
        db.add(repo)
        db.commit()
        repo_id = repo.id

    admitted = file_sessions()
    try:
        ensure_repository_admission(
            admitted, admitted.get(Repository, repo_id), OPERATION_BACKUP
        )
        with file_sessions() as other, pytest.raises(OperationalError, match="locked"):
            other.execute(
                text("UPDATE repositories SET name = 'blocked' WHERE id = :id"),
                {"id": repo_id},
            )
            other.commit()
    finally:
        admitted.rollback()
        admitted.close()
