"""Maintenance executors (spec 6.3 and section 13 phase 5).

Each executor is a thin shell. The work still lives in the service the kind
has always used, reached through `BorgRouter`, which picks the Borg 1, Borg 2,
or managed-agent path. The service drives the operation row through
`MaintenanceJobFacade`, so the shell's whole job is to load the repository,
run the router call, watch for cancellation, and turn the row's final status
into an `Outcome` for the runner.
"""

import asyncio
from datetime import datetime
from typing import Awaitable, Callable, Optional

import structlog

from app.core.borg_router import BorgRouter
from app.database.models import Operation, Repository, utc_now
from app.services.operations import executors
from app.services.operations.job_facade import MaintenanceJobFacade
from app.services.operations.runner import Outcome
from app.utils.db_retries import commit_with_retry

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


# The kinds whose Borg 2 server services claim the row through
# `claim_running` before they run.
_CLAIMING_KINDS = ("check", "prune", "compact", "delete_archive")


def _borg2_server_service(repository: Repository) -> bool:
    """Whether `BorgRouter` sends this repository's maintenance to a Borg 2
    server service (the v2 services), as opposed to a Borg 1 service or a
    managed agent."""
    from app.services.repository_executor import is_agent_executor

    return (repository.borg_version or 1) == 2 and not is_agent_executor(repository)


def _hands_over(ctx, repository: Repository) -> bool:
    """Whether this dispatch goes to a Borg 2 server service, the one route
    that claims the row through `claim_running`. The Borg 1 services write
    their own start over the runner's, the agent path leaves the row to the
    agent's report (which stamps the start from the job and would otherwise
    end a run with no start at all), and `restore_check` never claims."""
    return ctx.kind in _CLAIMING_KINDS and _borg2_server_service(repository)


async def _hand_over_to_service(ctx, claimed_at: Optional[datetime]) -> None:
    """Give the row the service the shape it claims. The runner's claim wrote
    `running` with a `started_at`; the Borg 2 server services claim the row
    again through `claim_running`, which takes a `running` row only without
    a start (the manual-start shape, so two dispatches of one id cannot both
    start), and skip the run otherwise. The runner is the one dispatcher
    here, so the start is the service's to record: it stamps its own when
    it claims. One guarded UPDATE, read from the table rather than this
    session's copy: only a row still `running` and still carrying the
    start this dispatch's claim wrote is cleared, so a cancel that landed
    in between keeps its start and a row another claim has since stamped
    is left alone. A row this dispatch did not claim with a start (the
    inline shape) is not touched either: a start it carries is not this
    dispatch's to clear. Committed with the retry every write on this path
    uses; the service runs in its own session."""
    if claimed_at is None:
        return

    cleared = 0

    def clear_start():
        nonlocal cleared
        cleared = (
            ctx.db.query(Operation)
            .filter(
                Operation.id == ctx.operation_id,
                Operation.status == "running",
                Operation.started_at == claimed_at,
            )
            .update({Operation.started_at: None}, synchronize_session=False)
        )

    await commit_with_retry(
        ctx.db,
        prepare=clear_start,
        logger=logger,
        action="maintenance_hand_over",
        operation_id=ctx.operation_id,
    )
    if not cleared:
        # A cancel landed since the claim, or the row is not this claim's:
        # the service will decline it and the executor reports that.
        logger.info(
            "Maintenance row not handed over, left as found",
            operation_id=ctx.operation_id,
            kind=ctx.kind,
        )


async def _run(
    ctx,
    call: Callable[[BorgRouter, int], Awaitable[None]],
    *,
    canceller: Optional[Callable[[int], Awaitable[bool]]] = None,
    borg2_canceller: Optional[Callable[[int], Awaitable[bool]]] = None,
) -> Outcome:
    """`canceller` is the Borg 1 service's, `borg2_canceller` the Borg 2
    service's; the one the router's route tracks the process is the one the
    watcher calls. The Borg 2 services also poll the row for `cancelled`,
    which the runner's cooperative flag never writes, so without their own
    canceller a cancel is not seen until the run finishes."""
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    if borg2_canceller is not None and _borg2_server_service(repository):
        canceller = borg2_canceller
    if _hands_over(ctx, repository):
        # The row is left with no start until the service claims it. A
        # service that never gets that far (a missing repository, a lock it
        # gave up on, a raise) leaves it that way, and the runner puts the
        # dispatch's start back when it writes the terminal state, so the
        # run keeps its place in the history and its duration.
        await _hand_over_to_service(ctx, ctx.operation.started_at)
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
    if status == "failed" and ctx.cancelled():
        # A killed process is a failure to the service: the row never read
        # `cancelled` (the runner's flag does not write it), so it recorded
        # the signal's exit code as the error. The service has returned, so
        # the process is dead and the lane can go: the verdict is the user's
        # cancel, which the runner keeps only when the row already says so.
        operation.status = "cancelled"
        ctx.db.commit()
        return Outcome(status="failed", error_message="cancelled")
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
    from app.services.v2.prune_service import prune_v2_service

    params = ctx.params
    retention = tuple(
        params.get(name, default) for name, default in _PRUNE_DEFAULTS.items()
    )
    keep_within = params.get("keep_within")
    kwargs = {"keep_within": keep_within} if keep_within is not None else {}

    async def call(router, job_id):
        await router.prune(job_id, *retention, False, **kwargs)

    return await _run(
        ctx,
        call,
        canceller=getattr(prune_service, "cancel_prune", None),
        borg2_canceller=getattr(prune_v2_service, "cancel_prune", None),
    )


executors.register("prune", run_prune)


async def run_compact(ctx) -> Outcome:
    from app.services.compact_service import compact_service
    from app.services.v2.compact_service import compact_v2_service

    return await _run(
        ctx,
        lambda router, job_id: router.compact(job_id),
        canceller=getattr(compact_service, "cancel_compact", None),
        borg2_canceller=getattr(compact_v2_service, "cancel_compact", None),
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
