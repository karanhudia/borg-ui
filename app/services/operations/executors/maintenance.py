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

# The row's words once a service is done. The facade writes the restore
# check's legacy `needs_backup` as `skipped` with that reason (spec 6.3).
_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled", "skipped")
_CANCEL_POLL_SECONDS = 1.0


def _load_repository(ctx) -> Optional[Repository]:
    if ctx.repository_id is None:
        return None
    return ctx.db.get(Repository, ctx.repository_id)


async def cancel_watcher(
    ctx, canceller: Optional[Callable[[int], Awaitable[bool]]]
) -> None:
    """Turn the runner's cooperative cancel flag (spec 7.7) into the process
    kill the legacy cancel routes performed. Returns once the process is
    actually terminated, or the task is cancelled from outside (`_run`'s
    `finally` does this once `call()` itself returns, cancelled or not)."""
    if canceller is None:
        return
    while True:
        if ctx.cancelled():
            try:
                # A cancel request can land before the service has registered
                # its process (still resolving the repository, listing
                # archives, etc.), so a single `False` doesn't mean the
                # operation won't be cancellable - keep retrying each poll
                # interval until it actually terminates something.
                if await canceller(ctx.operation_id):
                    return
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
        result = {"logs": bool(job.log_file_path)}
        if job.stats is not None:
            # A compact's `--stats` output, filed by the service under
            # `result["stats"]` (spec 6.1); the runner writes the row's
            # result from this outcome, so it has to travel through it.
            result["stats"] = job.stats
        return Outcome(status=status, result=result)
    if status == "cancelled":
        # `Outcome` has no cancelled status (spec 6.3 gives that to the row,
        # not to the executor's verdict), and the runner rewrites the row to
        # cancelled itself when it sees its own flag set. Report the failure
        # shape and let the runner have the last word.
        return Outcome(status="failed", error_message=job.error_message or "cancelled")
    if status == "skipped":
        return Outcome(
            status="skipped",
            skip_reason=operation.skip_reason,
            error_message=job.error_message,
        )
    return Outcome(status="failed", error_message=job.error_message)


async def run_check(ctx) -> Outcome:
    from app.services.check_service import check_service

    return await _run(
        ctx,
        lambda router, job_id: router.check(job_id),
        canceller=getattr(check_service, "cancel_check", None),
    )


executors.register("check", run_check)


_PRUNE_DEFAULTS = {
    "keep_hourly": 0,
    "keep_daily": 7,
    "keep_weekly": 4,
    "keep_monthly": 6,
    "keep_quarterly": 0,
    "keep_yearly": 1,
}


async def run_prune(ctx) -> Outcome:
    from app.services.prune_service import prune_service

    params = ctx.params
    retention = tuple(
        params.get(name, default) for name, default in _PRUNE_DEFAULTS.items()
    )
    keep_within = params.get("keep_within")
    kwargs = {"keep_within": keep_within} if keep_within is not None else {}

    async def call(router, job_id):
        await router.prune(job_id, *retention, False, **kwargs)

    return await _run(ctx, call, canceller=getattr(prune_service, "cancel_prune", None))


executors.register("prune", run_prune)


async def run_compact(ctx) -> Outcome:
    from app.services.compact_service import compact_service

    return await _run(
        ctx,
        lambda router, job_id: router.compact(job_id),
        canceller=getattr(compact_service, "cancel_compact", None),
    )


executors.register("compact", run_compact)


async def run_delete_archive(ctx) -> Outcome:
    from app.services.delete_archive_service import delete_archive_service

    archive_name = ctx.params.get("archive_name")
    if not archive_name:
        return Outcome(
            status="failed", error_message="delete_archive requires an archive name"
        )

    async def cancel(operation_id):
        return await delete_archive_service.cancel_delete(operation_id, ctx.db)

    return await _run(
        ctx,
        lambda router, job_id: router.delete_archive(job_id, archive_name),
        canceller=cancel,
    )


executors.register("delete_archive", run_delete_archive)


async def run_restore_check(ctx) -> Outcome:
    from app.services.restore_check_service import restore_check_service

    async def call(_router, job_id):
        await restore_check_service.execute_restore_check(job_id, ctx.repository_id)

    return await _run(
        ctx,
        call,
        canceller=getattr(restore_check_service, "cancel_restore_check", None),
    )


executors.register("restore_check", run_restore_check)
