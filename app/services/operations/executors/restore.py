"""The restore executor (spec 6.3, section 13 phase 7).

A thin shell in the shape phase 5's maintenance executors established: the
work stays in `restore_service.execute_restore`, which drives the row through
`RestoreJobFacade` down whichever of its three paths applies (local
destination, SSH destination over SSHFS, managed agent); the shell loads the
repository, hands the service the inputs the details row and `params` carry,
watches the runner's cancel flag, and turns the row's final status into an
`Outcome`.

Restore is not exclusive (spec 6.3, Appendix B) and the legacy service took no
repository lock, so neither does this shell.
"""

import asyncio

import structlog

from app.database.models import Operation, Repository
from app.services.operations import executors
from app.services.operations.executors.maintenance import cancel_watcher
from app.services.operations.restore_facade import (
    CANCEL_MESSAGES,
    CANCELLED_BY_USER,
    RestoreJobFacade,
)
from app.services.operations.runner import Outcome
from app.utils.restore_layout import RESTORE_LAYOUT_PRESERVE_PATH

logger = structlog.get_logger()

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


async def run_restore(ctx) -> Outcome:
    from app.services.restore_service import restore_service

    repository = (
        ctx.db.get(Repository, ctx.repository_id)
        if ctx.repository_id is not None
        else None
    )
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    job = RestoreJobFacade(ctx.db, ctx.db.get(Operation, ctx.operation_id))
    params = ctx.params
    watcher = asyncio.create_task(cancel_watcher(ctx, restore_service.cancel_restore))
    try:
        await restore_service.execute_restore(
            ctx.operation_id,
            repository.path,
            job.archive,
            job.destination,
            list(params.get("paths") or []),
            repository_type=job.repository_type or repository.repository_type,
            destination_type=job.destination_type or "local",
            destination_connection_id=job.destination_connection_id,
            ssh_connection_id=(
                repository.connection_id
                if repository.repository_type == "ssh"
                else None
            ),
            restore_layout=params.get("restore_layout") or RESTORE_LAYOUT_PRESERVE_PATH,
            path_metadata=list(params.get("path_metadata") or []),
        )
    finally:
        watcher.cancel()

    # The service ran in its own session and committed there. Expire this one
    # so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = RestoreJobFacade(ctx.db, operation)

    if ctx.cancelled():
        # The cancel route killed the process and wrote `cancelled`; the
        # service's read loop may have written `failed` for the killed process
        # after that. The flag is the truth (spec 7.7): restore the verdict
        # and the message the route chose, and let the runner keep it.
        operation.status = "cancelled"
        if operation.error_message not in CANCEL_MESSAGES:
            operation.error_message = CANCELLED_BY_USER
        ctx.db.commit()
        return Outcome(status="failed", error_message=operation.error_message)

    status = operation.status
    if status not in _TERMINAL:
        # Still running means the service returned without recording a
        # verdict, which is a bug in the service, not a success.
        return Outcome(
            status="failed",
            error_message=job.error_message or "restore returned no result",
        )
    if status in ("completed", "completed_with_warnings"):
        return Outcome(
            status=status,
            result={"nfiles": job.nfiles or 0, "restored_size": job.restored_size or 0},
        )
    # `Outcome` has no cancelled status (spec 6.3 gives that to the row, not to
    # the executor's verdict); a row the service itself marked cancelled (an
    # agent that reported `canceled`) reaches the runner as a failure shape
    # with the row already saying cancelled, and the runner keeps the row.
    return Outcome(status="failed", error_message=job.error_message)


executors.register("restore", run_restore)
