"""Run the operations runner against a test's own database.

Since phase 8 the schedule and plan entry points enqueue an operation and
wait for the runner to dispatch it, instead of running the backup inline. A
test that calls one of those functions directly therefore needs a runner
bound to the session it wrote the row through.

`OperationRunner` resolves its sessions through `_session_factory` when one
is set, which is what this helper uses. Without it the runner reads the
process-wide database that `tests/conftest.py` creates empty, never sees the
queued row, and the caller's wait never ends.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

# The `SessionLocal` aliases the backup path opens its own sessions through.
# The `test_db` fixture already patches these; a test on a bare `db_session`
# does not, and the executor would otherwise run against the empty
# process-wide database and log "Job not found".
_SESSION_LOCAL_ALIASES = (
    "app.database.database.SessionLocal",
    "app.services.backup_service.SessionLocal",
    "app.services.remote_backup_service.SessionLocal",
    "app.services.operations.reconcile.SessionLocal",
    "app.api.schedule.SessionLocal",
)


@asynccontextmanager
async def operations_runner_for(session, *, patch_session_local: bool = False):
    """A live runner dispatching the operations `session` can see.

    Set `patch_session_local` for a test that does not use the `test_db`
    fixture, so the services the executor calls open their sessions on this
    database too.
    """
    from app.services.operations.executors import load_default_executors
    from app.services.operations.runner import operation_runner

    load_default_executors()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=session.get_bind())
    previous_factory = operation_runner._session_factory
    operation_runner._session_factory = factory
    patches = (
        [patch(alias, factory) for alias in _SESSION_LOCAL_ALIASES]
        if patch_session_local
        else []
    )
    for started in patches:
        started.start()
    task = asyncio.create_task(operation_runner.start())
    try:
        yield operation_runner
    finally:
        for started in patches:
            started.stop()
        operation_runner.stop()
        try:
            await asyncio.wait_for(operation_runner.drain(), timeout=30)
        except (asyncio.TimeoutError, Exception):
            pass
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        operation_runner._session_factory = previous_factory
