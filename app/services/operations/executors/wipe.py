"""The wipe executor (spec 6.3, section 13 phase 6).

A thin shell in the shape phase 5's maintenance executors established: the
work stays in `repository_wipe_service.execute_wipe`, which drives the row
through `WipeJobFacade`; the shell loads the repository, runs the service, and
turns the row's final status into an `Outcome`. Wipe has no running-cancel
path today (`cancel_preview` refuses a running job), so no cancel watcher.
"""

import structlog

from app.database.models import Operation, Repository
from app.services.operations import executors
from app.services.operations.runner import Outcome
from app.services.operations.wipe_facade import WipeJobFacade

logger = structlog.get_logger()

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


async def run_wipe(ctx) -> Outcome:
    from app.services.repository_wipe_service import repository_wipe_service

    if ctx.repository_id is None or ctx.db.get(Repository, ctx.repository_id) is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    await repository_wipe_service.execute_wipe(ctx.operation_id, ctx.repository_id)

    # The service ran in its own session and committed there. Expire this one
    # so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = WipeJobFacade(ctx.db, operation)
    if operation.status not in _TERMINAL:
        # Still running means the service returned without recording a
        # verdict, which is a bug in the service, not a success.
        return Outcome(
            status="failed",
            error_message=job.error_message or "wipe returned no result",
        )
    if operation.status in ("completed", "completed_with_warnings"):
        return Outcome(
            status=operation.status,
            result={"archive_count": job.archive_count, "phase": job.phase},
        )
    # `Outcome` has no cancelled status (spec 6.3 gives that to the row, not to
    # the executor's verdict); the runner rewrites the row to cancelled itself
    # when it sees its own flag set. Report the failure shape and let the
    # runner have the last word.
    return Outcome(status="failed", error_message=job.error_message)


executors.register("wipe", run_wipe)
