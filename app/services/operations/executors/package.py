"""The package install executor (spec 6.3, section 13 phase 6).

`package_install` is category `system` with a null `repository_id`, so there is
no repository to load and no lane to take. The install body stays in
`package_service`; this shell runs it and reads the verdict back.
"""

import structlog

from app.database.models import Operation
from app.services.operations import executors
from app.services.operations.package_facade import PackageInstallFacade
from app.services.operations.runner import Outcome

logger = structlog.get_logger()

_TERMINAL = ("completed", "failed", "cancelled")


async def run_package_install(ctx) -> Outcome:
    from app.services.package_service import package_service

    await package_service.run_install_job(ctx.operation_id)

    # The service may have run in its own session; expire this one so the
    # verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = PackageInstallFacade(ctx.db, operation)
    if operation.status not in _TERMINAL:
        return Outcome(
            status="failed",
            error_message=job.error_message or "package install returned no result",
        )
    if operation.status == "completed":
        return Outcome(status="completed", result={"exit_code": job.exit_code})
    # `Outcome` has no cancelled status (spec 6.3 gives that to the row); the
    # runner rewrites the row itself when it sees its own cancel flag. The exit
    # code rides along: the runner replaces `result` with the outcome's, and a
    # failed install is exactly when a reader wants to see it.
    return Outcome(
        status="failed",
        error_message=job.error_message,
        result={"exit_code": job.exit_code},
    )


executors.register("package_install", run_package_install)
