"""The backup executor (spec 6.3, section 13 phase 8).

A thin shell in the shape phase 5 established: the work stays in
`backup_service.execute_backup` (local and SSHFS sources, or the remote
service it delegates to) or in the agent transport; the shell loads the
repository, hands the service or the agent queue the inputs `params`
carries, watches the runner's cancel flag, and turns the row's final status
into an `Outcome`. Notifications and MQTT publishes stay where they are: the
service sends them for server backups, the agent transport for agent
backups. The runner enqueues the index chain on success (spec 7.4); the one
failure that still changed the repository, a post-backup hook failing after
`borg create` succeeded, enqueues the chain from here (Appendix B).
"""

import asyncio
import json
from typing import Optional

import structlog

from app.database.models import Operation, Repository
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.operations import executors
from app.services.operations.backup_facade import (
    AGENT_PARAMS,
    CANCEL_MESSAGES,
    CANCELLED_BY_USER,
    POST_CREATE_FAILURE_KEYS,
    SERVICE_PARAMS,
    BackupJobFacade,
    resolve_backup_job,
)
from app.services.operations.executors.maintenance import cancel_watcher
from app.services.operations.runner import Outcome
from app.services.operations.vocab import TERMINAL_STATUSES
from app.services.repository_executor import (
    cancel_agent_backup_job,
    get_agent_job_for_backup,
    queue_agent_backup_job,
    wait_for_agent_backup_job,
)

logger = structlog.get_logger()

# The operations vocabulary, which includes `skipped`: a pre-backup script can
# stand the backup down gracefully, and `backup_service` writes that word and
# returns. Reading it as unfinished would record a failure instead.
_TERMINAL = TERMINAL_STATUSES


def _error_key(message: Optional[str]) -> Optional[str]:
    try:
        parsed = json.loads(message or "")
    except (TypeError, ValueError):
        return None
    return parsed.get("key") if isinstance(parsed, dict) else None


async def _cancel_server_backup(operation_id: int) -> bool:
    from app.services.backup_service import _uses_remote_execution, backup_service
    from app.services.remote_backup_service import remote_backup_service
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        job = resolve_backup_job(db, operation_id)
        remote = job is not None and _uses_remote_execution(job)
    finally:
        db.close()
    if remote:
        return await remote_backup_service.cancel_remote_backup(operation_id)
    return await backup_service.cancel_backup(operation_id)


async def _cancel_agent_backup(operation_id: int) -> bool:
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        job = resolve_backup_job(db, operation_id)
        if job is None:
            return True
        agent_job = get_agent_job_for_backup(db, job)
        if agent_job is None:
            return False
        cancel_agent_backup_job(db, job)
        db.commit()
        await dispatch_agent_cancel_if_connected(agent_job)
        return True
    finally:
        db.close()


def _enqueue_post_create_chain(ctx, operation: Operation) -> None:
    from app.services.operations.enqueue import enqueue_chain
    from app.services.operations.executors import registered_kinds
    from app.services.operations.followups import chain_for, history_enabled

    kinds = chain_for(
        "backup", available=registered_kinds(), history=history_enabled(ctx.db)
    )
    if not kinds:
        return
    enqueue_chain(
        ctx.db,
        kinds,
        repository_id=operation.repository_id,
        trigger="followup",
        run_id=operation.run_id,
        triggered_by_user_id=operation.triggered_by_user_id,
        scheduled_job_id=operation.scheduled_job_id,
        backup_plan_run_id=operation.backup_plan_run_id,
    )


async def run_backup(ctx) -> Outcome:
    from app.services.backup_service import backup_service

    repository = (
        ctx.db.get(Repository, ctx.repository_id)
        if ctx.repository_id is not None
        else None
    )
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    params = ctx.params
    job = BackupJobFacade(ctx.db, ctx.db.get(Operation, ctx.operation_id))

    if params.get("executor") == "agent":
        # Raises the admission's 409 while the repository is busy, which the
        # runner turns into a deferral (spec 7.1 step 5).
        agent_job = queue_agent_backup_job(
            ctx.db,
            job,
            repository,
            **{
                AGENT_PARAMS[key]: params[key]
                for key in AGENT_PARAMS
                if params.get(key) is not None
            },
        )
        ctx.db.commit()
        await dispatch_agent_job_best_effort(
            ctx.db,
            agent_job,
            source="operation_runner",
            operation_id=ctx.operation_id,
            repository_id=repository.id,
        )
        watcher = asyncio.create_task(cancel_watcher(ctx, _cancel_agent_backup))
        try:
            await wait_for_agent_backup_job(
                ctx.db, agent_job.id, ctx.operation_id, ctx.cancelled
            )
        finally:
            watcher.cancel()
    else:
        watcher = asyncio.create_task(cancel_watcher(ctx, _cancel_server_backup))
        try:
            await backup_service.execute_backup(
                ctx.operation_id,
                repository.path,
                None,
                **{key: params[key] for key in SERVICE_PARAMS if key in params},
            )
        finally:
            watcher.cancel()

    # The service ran in its own session and committed there. Expire this one
    # so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = BackupJobFacade(ctx.db, operation)

    if ctx.cancelled():
        operation.status = "cancelled"
        if operation.error_message not in CANCEL_MESSAGES:
            operation.error_message = CANCELLED_BY_USER
        ctx.db.commit()
        return Outcome(status="failed", error_message=operation.error_message)

    status = operation.status
    if status not in _TERMINAL:
        return Outcome(
            status="failed",
            error_message=job.error_message or "backup returned no result",
        )
    if status == "skipped":
        return Outcome(status="skipped", skip_reason=job.error_message)
    if status in ("completed", "completed_with_warnings"):
        return Outcome(
            status=status,
            result={
                "archive_name": job.archive_name,
                "original_size": job.original_size or 0,
                "compressed_size": job.compressed_size or 0,
                "deduplicated_size": job.deduplicated_size or 0,
                "nfiles": job.nfiles or 0,
            },
        )
    if status == "failed" and _error_key(job.error_message) in POST_CREATE_FAILURE_KEYS:
        _enqueue_post_create_chain(ctx, operation)
    return Outcome(status="failed", error_message=job.error_message)


executors.register("backup", run_backup)
