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
from sqlalchemy.exc import SQLAlchemyError

from app.core.borg_router import BorgRouter
from app.database.models import AgentJob, AgentMachine, Operation, Repository, utc_now
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


# An agent job that has not reached a verdict yet.
_LIVE_AGENT_JOB_STATUSES = ("queued", "claimed", "running", "cancel_requested")
_AGENT_CANCEL_ATTEMPTS = 3

# Advertised by an agent that ends a running job's Borg process when the
# job is cancelled, whatever Borg prints (0.1.7). An older one reports the job
# cancelled at once and lets a silent Borg run on, holding the repository.
AGENT_CANCEL_CAPABILITY = "jobs.cancel"


def _queued_cancel_values(now: datetime) -> dict:
    return {
        AgentJob.status: "canceled",
        AgentJob.completed_at: now,
        AgentJob.error_message: "Cancelled by user",
        AgentJob.updated_at: now,
    }


def take_queued_agent_job(
    db,
    repository: Repository,
    operation_id: int,
    *,
    agent_job_id: Optional[int] = None,
) -> bool:
    """Cancel the agent job that carries `operation_id` while no agent has
    taken it, which needs nothing from the agent. The write is conditional
    on `queued`: an agent that claims the job meanwhile wins, and False
    comes back. `agent_job_id` names the job whose payload carries no link
    to the operation (a restore's)."""
    if agent_job_id is None:
        job = _agent_job_for_operation(db, repository, operation_id)
        if job is None:
            return False
        agent_job_id = job.id
    changed = (
        db.query(AgentJob)
        .filter(AgentJob.id == agent_job_id, AgentJob.status == "queued")
        .update(_queued_cancel_values(datetime.utcnow()), synchronize_session=False)
    )
    db.commit()
    return bool(changed)


def agent_machine_stops_on_cancel(db, agent_machine_id: Optional[int]) -> bool:
    """Whether the agent stops a running job's Borg process on cancel."""
    agent = (
        db.get(AgentMachine, agent_machine_id) if agent_machine_id is not None else None
    )
    capabilities = (agent.capabilities if agent is not None else None) or []
    return AGENT_CANCEL_CAPABILITY in capabilities


def agent_stops_on_cancel(db, repository: Repository) -> bool:
    """Whether the repository's agent stops a running operation on cancel."""
    return agent_machine_stops_on_cancel(db, repository.agent_machine_id)


def _agent_job_for_operation(
    db,
    repository: Repository,
    operation_id: int,
    *,
    statuses: tuple[str, ...] = _LIVE_AGENT_JOB_STATUSES,
    since: Optional[datetime] = None,
):
    """The newest agent job in `statuses` that carries `operation_id`: a
    repository job of the repository's agent whose payload names the
    operation as its maintenance job (`operation.maintenance_job`). The
    payload is JSON, so the id is compared as an int, as
    `process_utils.active_agent_maintenance_refs` does."""
    query = db.query(AgentJob).filter(
        AgentJob.job_type == "repository",
        AgentJob.status.in_(statuses),
    )
    if repository.agent_machine_id is not None:
        query = query.filter(AgentJob.agent_machine_id == repository.agent_machine_id)
    if since is not None:
        # an operation's agent jobs are queued after it
        query = query.filter(AgentJob.created_at >= since)
    for job in query.order_by(AgentJob.id.desc()).all():
        payload = job.payload if isinstance(job.payload, dict) else {}
        link = (payload.get("operation") or {}).get("maintenance_job") or {}
        try:
            linked_id = int(link.get("id"))
        except (TypeError, ValueError):
            continue
        if linked_id == operation_id:
            return job
    return None


# Set on an agent job the server stops waiting for and asks to stop (the
# restore check's stall bound). Its `canceled` is not a user's cancel: the
# run has already failed, and the agent confirming the stop must not turn
# that into `cancelled`.
AGENT_WAIT_ABANDONED_MESSAGE = "Stopped by the server: the wait for the agent ended"


def _agent_cancel_took_effect(db, repository: Repository, operation: Operation) -> bool:
    """Whether the agent job that carried `operation` ended `canceled` and
    none is live any more: the cancel reached it, whether the runner's flag
    was set before (the watcher) or after (a route that took a queued job
    off first). A job the server itself stopped after its wait ended
    (`AGENT_WAIT_ABANDONED_MESSAGE`) is not a cancel."""
    if _agent_job_for_operation(db, repository, operation.id) is not None:
        return False
    canceled = _agent_job_for_operation(
        db,
        repository,
        operation.id,
        statuses=("canceled",),
        since=operation.created_at,
    )
    return (
        canceled is not None and canceled.error_message != AGENT_WAIT_ABANDONED_MESSAGE
    )


# Running kinds a cancel stops only through an agent that advertises
# `AGENT_CANCEL_CAPABILITY`; an older one checks for a cancel between
# output lines and finishes a silent Borg regardless.
AGENT_CANCEL_GATED_KINDS = frozenset(
    {"restore", "check", "compact", "prune", "delete_archive", "restore_check"}
)


def agent_run_cannot_stop(db, operation: Operation) -> bool:
    """Whether cancelling the running `operation` would leave Borg running
    on a managed agent that does not stop it (before 0.1.7). A job no such
    agent has taken yet needs nothing from it: it is taken off the queue
    here, atomically, so an agent that claims it meanwhile does not run work
    whose cancel was accepted."""
    from app.services.repository_executor import is_agent_executor

    if (
        operation.kind not in AGENT_CANCEL_GATED_KINDS
        or operation.repository_id is None
    ):
        return False
    repository = db.get(Repository, operation.repository_id)
    if repository is None or not is_agent_executor(repository):
        return False
    if agent_stops_on_cancel(db, repository):
        return False
    agent_job_id = None
    if operation.kind == "restore":
        # A restore's agent job carries no link to its operation.
        from app.services.restore_service import restore_service

        agent_job_id = restore_service.agent_restore_jobs.get(operation.id)
        if agent_job_id is None:
            return True
    return not take_queued_agent_job(
        db, repository, operation.id, agent_job_id=agent_job_id
    )


async def cancel_agent_operation_job(
    db, repository: Repository, operation_id: int
) -> bool:
    """Stop the agent job that runs `operation_id`, the managed agent's
    counterpart of killing the server's Borg process. A job no agent has
    taken yet is cancelled outright; a claimed or running one gets
    `cancel_requested`, which the agent reads from its heartbeat or the
    session's cancel command, stops Borg and reports `canceled`; an agent
    that would not stop it is left alone, and the run ends when Borg does.
    False while no job carries the operation yet or the command did not
    reach the agent, so the watcher asks again."""
    try:
        return await _request_agent_cancel(db, repository, operation_id)
    except SQLAlchemyError:
        # A database error must not end the watcher, which gives up on an
        # exception: the next poll asks again.
        db.rollback()
        return False


async def _request_agent_cancel(db, repository: Repository, operation_id: int) -> bool:
    from app.services.agent_job_dispatcher import dispatch_agent_cancel_if_connected

    for _ in range(_AGENT_CANCEL_ATTEMPTS):
        db.expire_all()
        job = _agent_job_for_operation(db, repository, operation_id)
        if job is None:
            return False
        observed = job.status
        if observed != "queued" and not agent_stops_on_cancel(db, repository):
            return True
        if observed == "cancel_requested":
            # A session agent learns of the cancel only from the command;
            # one that was not delivered (the agent was reconnecting) is
            # sent again on the next poll.
            return await dispatch_agent_cancel_if_connected(job)
        now = datetime.utcnow()
        if observed == "queued":
            values = _queued_cancel_values(now)
        else:
            values = {AgentJob.status: "cancel_requested", AgentJob.updated_at: now}
        # Conditional on the status just read: the agent's reports land
        # concurrently, and a claim between read and write must still get
        # the cancel, so a lost race reads again.
        changed = (
            db.query(AgentJob)
            .filter(AgentJob.id == job.id, AgentJob.status == observed)
            .update(values, synchronize_session=False)
        )
        db.commit()
        if not changed:
            continue
        if observed != "queued":
            db.refresh(job)
            return await dispatch_agent_cancel_if_connected(job)
        return True
    return False


# The kinds whose Borg 2 server services claim the row through
# `claim_running` before they run.
_CLAIMING_KINDS = ("check", "prune", "compact", "delete_archive")


def _borg2_server_service(repository: Repository) -> bool:
    """Whether `BorgRouter` sends this repository's maintenance to a Borg 2
    server service (the v2 services), as opposed to a Borg 1 service or a
    managed agent."""
    from app.services.repository_executor import is_agent_executor

    return (repository.borg_version or 1) == 2 and not is_agent_executor(repository)


def _agent_executed(repository: Repository) -> bool:
    from app.services.repository_executor import is_agent_executor

    return is_agent_executor(repository)


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
    if _agent_executed(repository):
        # The Borg process runs on the agent: the server has none to kill.

        async def agent_canceller(operation_id: int) -> bool:
            return await cancel_agent_operation_job(ctx.db, repository, operation_id)

        canceller = agent_canceller

    if _hands_over(ctx, repository):
        # The row is left with no start until the service claims it. A
        # service that never gets that far (a missing repository, a lock it
        # gave up on, a raise) leaves it that way, and the runner puts the
        # dispatch's start back when it writes the terminal state, so the
        # run keeps its place in the history and its duration.
        await _hand_over_to_service(ctx, ctx.operation.started_at)
    watcher = asyncio.create_task(cancel_watcher(ctx, canceller))
    try:
        # The kinds below pass `raise_busy`: an agent job the admission
        # refuses leaves this row as it is and raises the refusal, which the
        # runner defers, running the operation again on this row later.
        await call(BorgRouter(repository), ctx.operation_id)
    except Exception:
        # A cancelled agent job ends the router's wait with an error; the
        # row below says what the run came to. Not an error while the agent
        # job is still live (a wait that timed out): the agent has not
        # stopped Borg, so the run failed rather than being cancelled.
        if _agent_executed(repository):
            try:
                agent_cancelled = _agent_cancel_took_effect(
                    ctx.db, repository, ctx.db.get(Operation, ctx.operation_id)
                )
            except SQLAlchemyError:
                # The session may be what failed; the error the run met stands.
                ctx.db.rollback()
                raise
            if not agent_cancelled:
                raise
        elif not ctx.cancelled():
            raise
    finally:
        watcher.cancel()

    # The service ran in its own session and committed there. Expire this
    # one so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = MaintenanceJobFacade(ctx.db, operation)
    status = operation.status
    cancelled = False
    if status not in _TERMINAL or status == "failed":
        # Asked only where the answer decides the verdict.
        cancelled = ctx.cancelled() or (
            _agent_executed(repository)
            and _agent_cancel_took_effect(ctx.db, repository, operation)
        )
    if status not in _TERMINAL and cancelled:
        # An agent job cancelled before the agent took it reports nothing,
        # and nobody else writes the row: the user's cancel is the verdict.
        operation.status = "cancelled"
        ctx.db.commit()
        return Outcome(status="failed", error_message="cancelled")
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
    if status == "failed" and cancelled:
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
    from app.services.v2.check_service import check_v2_service

    return await _run(
        ctx,
        lambda router, job_id: router.check(job_id, raise_busy=True),
        canceller=getattr(check_service, "cancel_check", None),
        borg2_canceller=getattr(check_v2_service, "cancel_check", None),
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
        await router.prune(job_id, *retention, False, raise_busy=True, **kwargs)

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
        lambda router, job_id: router.compact(job_id, raise_busy=True),
        canceller=getattr(compact_service, "cancel_compact", None),
        borg2_canceller=getattr(compact_v2_service, "cancel_compact", None),
    )


executors.register("compact", run_compact)


async def run_delete_archive(ctx) -> Outcome:
    from app.services.delete_archive_service import delete_archive_service
    from app.services.v2.delete_archive_service import delete_archive_v2_service

    archive_name = ctx.params.get("archive_name")
    if not archive_name:
        return Outcome(
            status="failed", error_message="delete_archive requires an archive name"
        )

    async def cancel(operation_id):
        return await delete_archive_service.cancel_delete(operation_id, ctx.db)

    return await _run(
        ctx,
        lambda router, job_id: router.delete_archive(
            job_id, archive_name, raise_busy=True
        ),
        canceller=cancel,
        borg2_canceller=getattr(delete_archive_v2_service, "cancel_delete", None),
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
