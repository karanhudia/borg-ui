"""The rclone mirror executor (spec 6.3, 7.2, section 13 phase 6).

`rclone_sync` ignores the repository lane and takes the `rclone` lock scope
instead (spec 7.2). Two of the three pre-phase-6 dispatch paths wrapped the
call in that lock and the mirror scheduler did not, so the wrapping moves here
and every path gets it.

One kind covers both the mirror sync and the cache hydrate; `details.operation`
says which (spec 6.2), and each goes to the service entry point it always had.
"""

import asyncio

import structlog

from app.database.models import Operation, Repository, RepositoryStorage
from app.services.operations import executors
from app.services.operations.rclone_facade import RcloneSyncFacade
from app.services.operations.runner import Outcome
from app.services.repository_command_lock import run_serialized_repository_command

logger = structlog.get_logger()

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")
# Storage states that mean "a sync is in flight". A run that ends badly before
# `sync_repository` writes its own failure (a cancel, or a crash on the way in)
# would otherwise leave the repository stuck on one of these forever, which is
# what the deleted `_mark_background_rclone_sync_failed` used to prevent.
_IN_FLIGHT_STORAGE_STATUSES = ("syncing", "hydrating", "pending")


def _record_scheduled_run(db, repository_id: int) -> None:
    """Stamp when the scheduled mirror last ran. The pre-phase-6 scheduler did
    this itself, right after awaiting the sync; now that it only enqueues, the
    run that actually happened is here."""
    from app.database.models import utc_now

    storage = (
        db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository_id)
        .first()
    )
    if storage is None:
        return
    storage.last_scheduled_sync_at = utc_now()
    db.commit()


def _mark_storage_failed(db, repository_id: int, message: str) -> None:
    storage = (
        db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository_id)
        .first()
    )
    if storage is None or storage.sync_status not in _IN_FLIGHT_STORAGE_STATUSES:
        return
    storage.sync_status = "failed"
    storage.last_sync_error = message
    db.commit()


async def run_rclone_sync(ctx) -> Outcome:
    from app.services.rclone_repository_service import rclone_repository_service

    repository = (
        ctx.db.get(Repository, ctx.repository_id)
        if ctx.repository_id is not None
        else None
    )
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    job = RcloneSyncFacade(ctx.db, ctx.db.get(Operation, ctx.operation_id))
    is_hydrate = job.operation == "hydrate"
    triggered_by = job.triggered_by
    scheduled_for = job.scheduled_for

    async def call():
        if is_hydrate:
            return await rclone_repository_service.hydrate_repository(
                ctx.db, repository, job_id=ctx.operation_id
            )
        return await rclone_repository_service.sync_repository(
            ctx.db,
            repository,
            triggered_by=triggered_by,
            scheduled_for=scheduled_for,
            job_id=ctx.operation_id,
        )

    try:
        await run_serialized_repository_command(repository.id, call, scope="rclone")
    except asyncio.CancelledError:
        _mark_storage_failed(ctx.db, repository.id, "rclone sync was cancelled")
        raise

    # The service may have run in its own session; expire this one so the
    # verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = RcloneSyncFacade(ctx.db, operation)
    if triggered_by == "schedule":
        _record_scheduled_run(ctx.db, repository.id)
    if operation.status not in _TERMINAL:
        message = job.error_text or "rclone sync returned no result"
        _mark_storage_failed(ctx.db, repository.id, message)
        return Outcome(status="failed", error_message=message)
    if operation.status in ("completed", "completed_with_warnings"):
        return Outcome(status=operation.status)
    # `Outcome` has no cancelled status (spec 6.3 gives that to the row); the
    # runner rewrites the row itself when it sees its own cancel flag.
    message = job.error_text or "rclone sync failed"
    _mark_storage_failed(ctx.db, repository.id, message)
    return Outcome(status="failed", error_message=job.error_text)


executors.register("rclone_sync", run_rclone_sync)
