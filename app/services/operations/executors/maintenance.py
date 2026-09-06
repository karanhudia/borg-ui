"""Maintenance executors (spec 6.3 and section 13 phase 5).

Each executor is a thin shell. The work still lives in the service the kind
has always used, reached through `BorgRouter`, which picks the Borg 1, Borg 2,
or managed-agent path. The service drives the operation row through
`MaintenanceJobFacade`, so the shell's whole job is to load the repository,
run the router call, watch for cancellation, and turn the row's final status
into an `Outcome` for the runner.
"""

import asyncio
from typing import Awaitable, Callable, Optional

import structlog

from app.core.borg_router import BorgRouter
from app.database.models import Operation, Repository, utc_now
from app.services.operations import executors
from app.services.operations.job_facade import MaintenanceJobFacade
from app.services.operations.runner import Outcome

logger = structlog.get_logger()

# Kinds that stamp a "last done" column on the repository when they succeed,
# the way the legacy services did from inside their own bodies.
_LAST_DONE_COLUMN = {"check": "last_check", "compact": "last_compact"}

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")
_CANCEL_POLL_SECONDS = 1.0


def _load_repository(ctx) -> Optional[Repository]:
    if ctx.repository_id is None:
        return None
    return ctx.db.get(Repository, ctx.repository_id)


async def cancel_watcher(
    ctx, canceller: Optional[Callable[[int], Awaitable[bool]]]
) -> None:
    """Turn the runner's cooperative cancel flag (spec 7.7) into the process
    kill the legacy cancel routes performed. Returns when the flag is seen or
    the task is cancelled."""
    if canceller is None:
        return
    while True:
        if ctx.cancelled():
            try:
                await canceller(ctx.operation_id)
            except Exception as exc:
                logger.warning(
                    "Maintenance cancel failed",
                    operation_id=ctx.operation_id,
                    error=str(exc),
                )
            return
        await asyncio.sleep(_CANCEL_POLL_SECONDS)


async def _run(
    ctx,
    call: Callable[[BorgRouter, int], Awaitable[None]],
    *,
    canceller: Optional[Callable[[int], Awaitable[bool]]] = None,
) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    watcher = asyncio.create_task(cancel_watcher(ctx, canceller))
    try:
        await call(BorgRouter(repository), ctx.operation_id)
    finally:
        watcher.cancel()

    # The service ran in its own session and committed there. Expire this
    # one so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = MaintenanceJobFacade(ctx.db, operation)
    status = operation.status
    if status not in _TERMINAL:
        # Still running means the service returned without recording a
        # verdict, which is a bug in the service, not a success.
        return Outcome(
            status="failed",
            error_message=job.error_message or "service returned no result",
        )
    if status in ("completed", "completed_with_warnings"):
        column = _LAST_DONE_COLUMN.get(ctx.kind)
        if column is not None:
            repository = ctx.db.get(Repository, ctx.repository_id)
            if repository is not None:
                setattr(repository, column, utc_now())
                ctx.db.commit()
        return Outcome(status=status, result={"logs": bool(job.log_file_path)})
    if status == "cancelled":
        # `Outcome` has no cancelled status (spec 6.3 gives that to the row,
        # not to the executor's verdict), and the runner rewrites the row to
        # cancelled itself when it sees its own flag set. Report the failure
        # shape and let the runner have the last word.
        return Outcome(status="failed", error_message=job.error_message or "cancelled")
    return Outcome(status="failed", error_message=job.error_message)


async def run_check(ctx) -> Outcome:
    from app.services.check_service import check_service

    return await _run(
        ctx,
        lambda router, job_id: router.check(job_id),
        canceller=getattr(check_service, "cancel_check", None),
    )


executors.register("check", run_check)
