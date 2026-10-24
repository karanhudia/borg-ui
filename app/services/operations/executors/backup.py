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

An agent repository's own hooks are agent scripts, run from here around the
agent backup (`_run_agent_backup`); a failure they cause after the agent
transport has notified is notified from here.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

import structlog

from app.database.models import Operation, Repository, ScriptExecution
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.operations import executors
from app.services.operations.backup_facade import (
    AGENT_PARAMS,
    CANCEL_MESSAGES,
    CANCELLED_BY_USER,
    SERVICE_PARAMS,
    BackupJobFacade,
    admission_ignore_for,
    backup_result_summary,
    failed_after_create,
    resolve_backup_job,
)
from app.services.operations.executors.maintenance import cancel_watcher
from app.services.operations.runner import Outcome
from app.services.operations.vocab import TERMINAL_STATUSES
from app.services.agent_job_notifications import notify_backup_job_finished
from app.services.agent_presence import AGENT_OFFLINE_SKIP_REASON
from app.services.agent_repository_hooks import (
    SKIPPED,
    AgentHookResult,
    agent_hooks,
    run_agent_repository_hooks,
    unrunnable_repository_scripts,
)
from app.services.job_admission import (
    ACTIVE_AGENT_STATUSES,
    OPERATION_BACKUP,
    ensure_repository_admission,
)
from app.services.repository_executor import (
    EXECUTOR_AGENT,
    cancel_agent_backup_job,
    get_agent_job_for_backup,
    is_agent_executor,
    queue_agent_backup_job,
    wait_for_agent_backup_job,
)

logger = structlog.get_logger()

# The operations vocabulary, which includes `skipped`: a pre-backup script can
# stand the backup down gracefully, and `backup_service` writes that word and
# returns. Reading it as unfinished would record a failure instead.
_TERMINAL = TERMINAL_STATUSES


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
    from app.services.operations.followups import enqueue_followups

    # The archive exists although the row failed, so the chain hangs off
    # nothing rather than inheriting the failure.
    enqueue_followups(ctx.db, operation, depends_on_id=None)


async def _queue_and_wait_agent_backup(ctx, job, repository, params) -> None:
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


def _hook_failure_message(key: str, hooks) -> str:
    return json.dumps(
        {"key": key, "params": {"failed": hooks.failed, "total": hooks.executed}}
    )


async def _run_post_hooks(ctx, repository, backup_result: str) -> AgentHookResult:
    """The post-backup hooks. An exception one of them raises is logged and
    counted as a failed hook, from the records they left, and never raised in
    place of the operation's own outcome: a cancel stays a cancel, and a busy
    repository's 409 still reaches the runner as a deferral."""
    try:
        return await run_agent_repository_hooks(
            ctx.db,
            repository,
            operation_id=ctx.operation_id,
            hook_type="post-backup",
            backup_result=backup_result,
        )
    except Exception as exc:
        ctx.db.rollback()
        logger.warning(
            "Post-backup hooks raised",
            operation_id=ctx.operation_id,
            repository_id=repository.id,
            error=str(exc),
        )
        statuses = [
            row.status
            for row in ctx.db.query(ScriptExecution.status).filter(
                ScriptExecution.operation_id == ctx.operation_id,
                ScriptExecution.hook_type == "post-backup",
            )
        ]
        failed = sum(1 for status in statuses if status not in ("completed", "warning"))
        return AgentHookResult(executed=max(len(statuses), 1), failed=max(failed, 1))


def _pre_hooks_ran(db, operation_id: int) -> bool:
    """Whether a pre-backup hook of this backup started, from the record
    each one leaves (`script_executions`)."""
    return (
        db.query(ScriptExecution.id)
        .filter(
            ScriptExecution.operation_id == operation_id,
            ScriptExecution.hook_type == "pre-backup",
        )
        .first()
        is not None
    )


async def _run_agent_backup(ctx, job, repository, params) -> None:
    """An agent backup with the repository's own hooks around it (#1386).

    The hooks are agent scripts the server asks the agent to run
    (`agent_repository_hooks`), before and after the backup the agent runs.
    Once a pre-backup hook ran, the post-backup hooks run on every way out,
    a failed pre-backup hook, a skip and an error before the backup
    included, so a service a pre-backup hook stopped is started again. A
    backup resumed after a restart waits on its live agent job and runs no
    pre-backup hook a second time. The verdict is left on the row for
    `run_backup` to read.
    """
    db = ctx.db
    if params.get("skip_hooks"):
        await _queue_and_wait_agent_backup(ctx, job, repository, params)
        return

    unrunnable = unrunnable_repository_scripts(db, repository)
    live_job = get_agent_job_for_backup(db, job)
    resuming = live_job is not None and live_job.status in ACTIVE_AGENT_STATUSES
    warnings: list[str] = []
    pre_ran = False
    if not resuming:
        # A busy repository defers before any hook ran, not after.
        ensure_repository_admission(
            db, repository, OPERATION_BACKUP, ignore=admission_ignore_for(job)
        )
        try:
            pre = await run_agent_repository_hooks(
                db,
                repository,
                operation_id=ctx.operation_id,
                hook_type="pre-backup",
                is_cancelled=ctx.cancelled,
            )
        except Exception:
            # a hook that ran before the error is undone all the same
            db.rollback()
            if _pre_hooks_ran(db, ctx.operation_id):
                await _run_post_hooks(ctx, repository, "failure")
            raise
        pre_ran = pre.executed > 0
        warnings.extend(pre.warnings)
        if pre.skip_script:
            # what the pre-backup hooks did, the skipping one included, is
            # undone by the post-backup hooks that run "always"
            post = await _run_post_hooks(ctx, repository, SKIPPED)
            job.completed_at = datetime.utcnow()
            if post.success:
                job.status = "skipped"
                job.error_message = f"Skipped by '{pre.skip_script}'"
                db.commit()
                return
            # a skip whose cleanup failed is not a graceful one
            job.status = "failed"
            job.error_message = _hook_failure_message(
                "backend.errors.service.postBackupHooksAlsoFailed", post
            )
            db.commit()
            await notify_backup_job_finished(db, job)
            return
        if not pre.success and not repository.continue_on_hook_failure:
            post = await _run_post_hooks(ctx, repository, "failure")
            job.status = "failed"
            job.error_message = _hook_failure_message(
                "backend.errors.service.preBackupHooksFailed", pre
            )
            if not post.success:
                job.error_message += "\n" + _hook_failure_message(
                    "backend.errors.service.postBackupHooksAlsoFailed", post
                )
            job.completed_at = datetime.utcnow()
            db.commit()
            await notify_backup_job_finished(db, job)
            return
        if not pre.success:
            # continue_on_hook_failure: the backup goes on, and says why
            warnings.extend(pre.failures)
        if ctx.cancelled():
            if pre_ran:
                await _run_post_hooks(ctx, repository, "failure")
            return

    try:
        await _queue_and_wait_agent_backup(ctx, job, repository, params)
    except Exception:
        if pre_ran:
            db.rollback()
            await _run_post_hooks(ctx, repository, "failure")
        raise

    db.expire_all()
    job = BackupJobFacade(db, db.get(Operation, ctx.operation_id))
    if job.operation.skip_reason == AGENT_OFFLINE_SKIP_REASON and not (
        pre_ran or _pre_hooks_ran(db, ctx.operation_id)
    ):
        # The agent never got the backup (#1331), and has nothing to undo:
        # its post-backup hooks would only wait for it as well. Once a
        # pre-backup hook ran, in this run or before a restart it resumed
        # from, they run, so a service it stopped is started again when the
        # agent is back.
        return
    status = "cancelled" if ctx.cancelled() else job.status
    backup_result = {
        "completed": "success",
        "completed_with_warnings": "warning",
        # skipped after a pre-backup hook ran (#1331): the hooks hear what
        # they hear after a skipping pre-backup hook
        "skipped": SKIPPED,
    }.get(status, "failure")
    if backup_result == "success" and (unrunnable or warnings):
        # the backup ends with a warning, and its post-backup hooks hear so,
        # as they do after the server's rclone mirror warns
        backup_result = "warning"
    post = None
    if agent_hooks(db, repository, "post-backup", backup_result):
        # The agent transport has ended the row; it stays ended, so a restart
        # under the hooks keeps the agent's verdict. The runner holds the
        # repository's lane while this task runs (`_lanes_held`).
        post = await _run_post_hooks(ctx, repository, backup_result)
        warnings.extend(post.warnings)
        db.expire_all()
        job = BackupJobFacade(db, db.get(Operation, ctx.operation_id))

    # The agent transport has notified the agent's verdict; a change the
    # hooks make to it is notified here.
    if post is not None and not post.success:
        if status in ("completed", "completed_with_warnings"):
            # the archive exists; `run_backup` enqueues its index chain
            job.status = "failed"
            job.error_message = _hook_failure_message(
                "backend.errors.service.postBackupHooksFailed"
                if status == "completed"
                else "backend.errors.service.backupWarningPostHooksFailed",
                post,
            )
            db.commit()
            await notify_backup_job_finished(db, job)
        elif status == "failed":
            job.error_message = (job.error_message or "") + (
                "\n"
                + _hook_failure_message(
                    "backend.errors.service.postBackupHooksAlsoFailed", post
                )
            )
            db.commit()
        elif status == "skipped":
            # a skip whose cleanup failed is not a graceful one: what a
            # pre-backup hook stopped may still be stopped (#1331)
            job.status = "failed"
            job.error_message = (job.error_message or "") + (
                "\n"
                + _hook_failure_message(
                    "backend.errors.service.postBackupHooksAlsoFailed", post
                )
            )
            db.commit()
            await notify_backup_job_finished(db, job)
    elif status == "completed" and (unrunnable or warnings):
        job.status = "completed_with_warnings"
        messages = []
        if unrunnable:
            messages.append(
                {
                    "key": "backend.errors.service.agentRepositoryScriptsNotRun",
                    "params": {"scripts": ", ".join(unrunnable)},
                }
            )
        if warnings:
            messages.append(
                {
                    "key": "backend.errors.service.repositoryHookWarnings",
                    "params": {"warnings": "; ".join(warnings)},
                }
            )
        job.error_message = "\n".join(json.dumps(m) for m in messages)
        db.commit()
        await notify_backup_job_finished(db, job)


def _backup_executor(ctx, job, repository) -> str:
    """Where the backup runs, decided now from the repository's current
    executor rather than the one it was queued with: a repository moved to
    an agent (or back) while the backup waited has its Borg on the other
    side now. A backup resumed after a restart whose agent job is still live
    stays with that job."""
    if is_agent_executor(repository):
        return EXECUTOR_AGENT
    if ctx.params.get("executor") == EXECUTOR_AGENT:
        live_job = get_agent_job_for_backup(ctx.db, job)
        if live_job is not None and live_job.status in ACTIVE_AGENT_STATUSES:
            return EXECUTOR_AGENT
    return "server"


def _record_backup_executor(ctx, job, repository, executor: str) -> None:
    """Store a changed executor on the row, with the execution mode the
    creation site would have given it, so the cancel path and the UI read
    where the backup runs."""
    from app.services.backup_route_planner import apply_repository_route_to_backup_job

    operation = ctx.db.get(Operation, ctx.operation_id)
    logger.info(
        "Backup executor follows the repository",
        operation_id=ctx.operation_id,
        repository_id=repository.id,
        queued_executor=ctx.params.get("executor"),
        executor=executor,
    )
    operation.params = {**(operation.params or {}), "executor": executor}
    if executor == EXECUTOR_AGENT:
        job.route_strategy = None
        job.execution_mode = EXECUTOR_AGENT
    else:
        job.execution_mode = "local"
        apply_repository_route_to_backup_job(job, repository)
    ctx.db.commit()


def _sources_refusal(repository, params) -> Optional[str]:
    """The error a backup that changes executor gets for the source
    locations it was queued with (a plan's), or None. An agent's paths are
    no server paths, nor the other way round, so they are checked against
    the repository's new executor as the plan route checks them."""
    from app.services.backup_route_planner import plan_repository_route

    source_locations = params.get("source_locations")
    if not source_locations:
        return None
    route = plan_repository_route(repository, source_locations)
    if route.supported:
        return None
    return json.dumps({"key": route.reason_key, "params": route.display_params})


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

    executor = _backup_executor(ctx, job, repository)
    if executor != (params.get("executor") or "server"):
        refusal = _sources_refusal(repository, params)
        if refusal is not None:
            job.status = "failed"
            job.error_message = refusal
            job.completed_at = datetime.utcnow()
            ctx.db.commit()
            return Outcome(status="failed", error_message=refusal)
        _record_backup_executor(ctx, job, repository, executor)
    if executor == EXECUTOR_AGENT:
        await _run_agent_backup(ctx, job, repository, params)
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
        if operation.skip_reason == AGENT_OFFLINE_SKIP_REASON:
            # the reaper's skip keeps its reason and says why (#1331)
            return Outcome(
                status="skipped",
                skip_reason=operation.skip_reason,
                error_message=job.error_message,
            )
        return Outcome(status="skipped", skip_reason=job.error_message)
    if status in ("completed", "completed_with_warnings"):
        return Outcome(
            status=status,
            result=backup_result_summary(job),
            # the runner writes the outcome's message onto the row: a
            # warning keeps the one that says what it was
            error_message=(
                job.error_message if status == "completed_with_warnings" else None
            ),
        )
    if failed_after_create(status, job.error_message):
        _enqueue_post_create_chain(ctx, operation)
    return Outcome(status="failed", error_message=job.error_message)


executors.register("backup", run_backup)
