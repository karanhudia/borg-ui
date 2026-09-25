"""The operations runner (spec section 7): loop, lanes, dispatch, follow-ups,
cancellation, and crash recovery. One instance per process."""

import asyncio
import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import structlog
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

import app.config as app_config
from app.core.borg_errors import LOCK_CONTENTION_DETAIL_KEY
from app.database.models import (
    Operation,
    OperationsRunnerLease,
    Repository,
    SystemSettings,
    utc_now,
)
from app.services.operations import executors as executor_registry
from app.services.operations.events import (
    broadcast_operation_progress,
    broadcast_operation_updated,
)
from app.services.operations.followups import enqueue_followups
from app.services.operations.lanes import can_start
from app.services.operations.vocab import INDEX_KINDS, SUCCESS_STATUSES, is_exclusive
from app.utils.process_utils import is_process_alive

logger = structlog.get_logger()

# An intentional skip lets dependants run, but a skip caused by a failed
# dependency must propagate the failure through the remaining chain.
# Executors that need a predecessor's result read it defensively.
_FAILED_DEPENDENCY_STATUSES = ("failed", "cancelled")
_SATISFIED_DEPENDENCY_STATUSES = SUCCESS_STATUSES | {"skipped"}
# What an executor may return. A deferral is not among them: it is the
# runner's own reaction to the admission's 409 and never an executor's
# choice, so an executor cannot requeue itself by accident.
_OUTCOME_STATUSES = (
    "completed",
    "completed_with_warnings",
    "skipped",
    "failed",
)
# An operation refused by the repository admission (another job holds the
# repository) goes back to the queue instead of failing: the backup
# follow-up listing is enqueued the instant the backup completes, while the
# plan is still creating its prune job, so the lane check can run before the
# prune row exists and admission then refuses the listing. Bounded, so a
# repository that never frees up still ends in a visible failure.
MAX_DEFERRALS = 20
# How often an index row left `running` without a live task is put back to
# `queued` before it fails: a terminal commit that keeps failing (a locked
# database, a full disk) would otherwise re-run the listing every tick.
MAX_REQUEUES = 3
# Each deferral waits before the next attempt, doubling from 5 s to 5 min.
# The runner is woken by every completion anywhere in the system, so without
# the delay a busy install would spend the whole deferral budget in seconds
# while a pending prune sits on the repository. 20 attempts give a
# repository about 75 minutes to free up.
DEFERRAL_DELAY_SECONDS = 5.0
DEFERRAL_MAX_DELAY_SECONDS = 300.0
# How long the runner lease outlives its last renewal (#1166): a holder that
# died without releasing it keeps a replacement waiting this long. Renewed
# every tick, and it has to outlast the tick before `stop()` plus the
# `drain()` after it, whose end releases it.
LEASE_SECONDS = 60.0
REPOSITORY_BUSY_KEY = "backend.errors.jobs.repositoryOperationActive"
# The errors a database that is locked, gone or out of connections raises:
# an outcome whose write fails with one of these is written again on a later
# tick, for as long as it takes. Anything else does not go away by waiting.
TRANSIENT_DATABASE_ERRORS = (OperationalError, InterfaceError, PoolTimeoutError)


def deferred_until(op: Operation) -> Optional[float]:
    """The not-before time (epoch seconds) of a deferred operation, if any."""
    raw = (op.params or {}).get("deferred_until")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    # inf would park the operation forever, nan would skip the backoff
    return value if math.isfinite(value) else None


def deferral_count(op: Operation) -> int:
    """How often the operation has been deferred; unreadable bookkeeping
    counts as none rather than crashing the runner."""
    try:
        count = int((op.params or {}).get("deferrals", 0))
    except (TypeError, ValueError, OverflowError):
        # inf overflows int(), nan and text are ValueErrors
        return 0
    return max(count, 0)


def requeue_count(op: Operation) -> int:
    """How often recovery has requeued the abandoned row; unreadable
    bookkeeping counts as none, like `deferral_count`."""
    params = op.params if isinstance(op.params, dict) else {}
    try:
        count = int(params.get("requeues", 0))
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(count, 0)


def repository_busy(exc: BaseException) -> bool:
    """True when the repository is taken for now: the admission's 409
    (repositoryOperationActive), or the waiter's 502 for an agent job whose
    Borg run ended on a lock another process holds (marked
    `lock_contention`, see `wait_for_agent_repository_operation_job`). Both
    are deferred the same way."""
    detail = getattr(exc, "detail", None)
    if not isinstance(detail, dict):
        return False
    status_code = getattr(exc, "status_code", None)
    if status_code == 409:
        return detail.get("key") == REPOSITORY_BUSY_KEY
    return status_code == 502 and detail.get(LOCK_CONTENTION_DETAIL_KEY) is True


@dataclass
class Outcome:
    status: str = "completed"
    result: Optional[dict] = None
    skip_reason: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.status not in _OUTCOME_STATUSES:
            raise ValueError(f"Invalid outcome status: {self.status!r}")


@dataclass
class _UnrecordedOutcome:
    """The terminal state a task of this runner reached but could not
    commit: what `run_operation` would have written. `kind`,
    `repository_id` and `run_id` identify the row beyond its id, which
    SQLite hands out again once the last row is deleted; `fallback` marks a
    failure the runner made up for a task that ended before any outcome,
    which only a row still `running` takes."""

    kind: str
    repository_id: Optional[int]
    run_id: str
    status: str
    result: Optional[dict]
    skip_reason: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: datetime
    fallback: bool = False
    # one more try after an error that is not the database's
    retried: bool = False


def operation_log_path(operation_id: int) -> Path:
    return Path(app_config.settings.data_dir) / "logs" / f"operation_{operation_id}.log"


class OperationContext:
    """What an executor gets: the row's identity, a session, progress, logs,
    and a cancellation check."""

    def __init__(self, runner: "OperationRunner", db: Session, operation: Operation):
        self._runner = runner
        self.db = db
        self.operation = operation
        self.operation_id = operation.id
        self.repository_id = operation.repository_id
        self.kind = operation.kind
        self.params = dict(operation.params or {})
        self._last_progress_write = 0.0
        self._log_handle = None

    def cancelled(self) -> bool:
        return self.operation_id in self._runner.cancel_requested

    async def progress(
        self,
        *,
        percent: Optional[float] = None,
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        now = time.monotonic()
        final = current is not None and total is not None and current >= total
        if not final and now - self._last_progress_write < 1.0:
            return
        self._last_progress_write = now
        op = self.operation
        if percent is not None:
            op.progress_percent = percent
        if current is not None:
            op.progress_current = current
        if total is not None:
            op.progress_total = total
        if message is not None:
            op.progress_message = message
        self.db.commit()
        await broadcast_operation_progress(op, self.db)

    def log(self, line: str) -> None:
        if self._log_handle is None:
            path = operation_log_path(self.operation_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = path.open("a", encoding="utf-8")
            if self.operation.log_file_path != str(path):
                self.operation.log_file_path = str(path)
                self.db.commit()
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def close(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


class OperationRunner:
    def __init__(
        self,
        *,
        session_factory=None,
        registry=None,
        poll_interval: float = 5.0,
        deferral_delay: float = DEFERRAL_DELAY_SECONDS,
        lease_seconds: float = LEASE_SECONDS,
    ):
        self._session_factory = session_factory
        self._registry = (
            registry if registry is not None else executor_registry.REGISTRY
        )
        self._poll_interval = poll_interval
        self._deferral_delay = deferral_delay
        self._lease_seconds = lease_seconds
        self._lease_holder = uuid.uuid4().hex
        # None until the first attempt, so a runner that starts without the
        # lease says it is waiting
        self._holds_lease: Optional[bool] = None
        # True once `start()`'s loop has returned: no tick can claim after it
        self._loop_exited = True
        # Set by a drain that timed out: its tasks were cancelled, not
        # finished, and what they started may outlive them
        self._drain_timed_out = False
        self._wake: Optional[asyncio.Event] = None
        self._stopped = False
        self.running_tasks: dict[int, asyncio.Task] = {}
        self.cancel_requested: set[int] = set()
        # Outcomes of this runner's own tasks whose terminal commit failed,
        # by operation id; the tick writes them (`record_unrecorded_outcomes`).
        self.unrecorded_outcomes: dict[int, _UnrecordedOutcome] = {}

    def _session(self) -> Session:
        """Open a session. Resolved lazily so test fixtures that patch
        app.database.database.SessionLocal reach the runner too."""
        if self._session_factory is not None:
            return self._session_factory()
        from app.database.database import SessionLocal

        return SessionLocal()

    # -- registry helpers (respect an injected registry in tests) ------------

    def _get_executor(self, kind: str):
        return self._registry.get(kind)

    def _registered_kinds(self) -> set[str]:
        return set(self._registry)

    def deferral_delay_for(self, deferrals: int) -> float:
        """Seconds to wait before the attempt after the n-th deferral."""
        return min(
            self._deferral_delay * 2 ** max(deferrals - 1, 0),
            DEFERRAL_MAX_DELAY_SECONDS,
        )

    # -- loop ------------------------------------------------------------------

    def _event(self) -> asyncio.Event:
        if self._wake is None:
            self._wake = asyncio.Event()
        return self._wake

    def wake(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._event().set()

    def stop(self) -> None:
        self._stopped = True

    async def drain(self, timeout: float = 30.0) -> None:
        """Request cooperative cancellation for every running task and wait
        for them to finish, so shutdown goes through
        `OperationContext.cancelled()` instead of a raw task cancellation.
        Call `stop()` first so no new tasks start while draining.

        A dispatched entry is normally a real `asyncio.Task`, but a test that
        patches `asyncio.create_task` around a request can catch this
        runner's own `tick()` dispatching newly enqueued work on the same
        event loop mid-request, landing a `MagicMock` in `running_tasks`
        instead. `asyncio.gather` raises `TypeError` outright on anything
        that isn't awaitable, which would otherwise crash every shutdown
        from that point on; filter those out instead of gathering them."""
        tasks = [t for t in self.running_tasks.values() if asyncio.isfuture(t)]
        if not tasks:
            self._release_lease_if_idle()
            return
        for operation_id in list(self.running_tasks):
            await self.request_cancel(operation_id)
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Operations runner drain timed out",
                remaining=len(self.running_tasks),
            )
            # the lease stays and expires rather than hand that over
            self._drain_timed_out = True
            return
        self._release_lease_if_idle()

    async def start(self, before_recovery: Optional[Callable[[], None]] = None) -> None:
        """`before_recovery` runs once, as this runner's recovery does, when
        it first holds the lease: the startup sweeps outside the runner touch
        rows a process being replaced may still own too."""
        self._stopped = False
        self._loop_exited = False
        self._drain_timed_out = False
        # A fresh `asyncio.Event` every time: the one from a previous call
        # is bound to that call's event loop (asyncio.Event binds to the
        # loop of its first `wait()`/`clear()`), and reusing it here after
        # that loop closed raises "bound to a different event loop" the
        # instant this loop's `wait()` runs. That's uncaught, so it kills
        # this coroutine right there; nothing awaits it until shutdown's
        # `gather(..., return_exceptions=True)`, which swallows it, so the
        # runner silently stops dispatching for the rest of the process.
        # Production runs `start()` once per process and never hits this;
        # a test suite that builds a fresh app (and event loop) per test
        # does, every time.
        self._wake = asyncio.Event()
        # Same reasoning as `_wake`: a task from a previous `start()` belongs
        # to that call's (closed) event loop and can never be gathered by
        # this one's `drain()` anyway. Without this, a task that failed to
        # dispatch as a real `asyncio.Task` (e.g. a test patching
        # `asyncio.create_task` at the exact moment this runner's own tick
        # fires) sits in `running_tasks` forever, since nothing ever
        # completes it to trigger the normal `.pop()` cleanup below - and
        # the next process-lifetime's `drain()` crashes trying to `gather()`
        # it (`TypeError: ... a coroutine or an awaitable is required`).
        self.running_tasks = {}
        # Same reasoning: those rows belong to a previous lifetime's database
        # session, and `recover_on_startup` owns rows left running across one.
        self.unrecorded_outcomes = {}
        logger.info("Operations runner started", poll_interval=self._poll_interval)
        recovered = False
        try:
            while not self._stopped:
                # Recovery, the sweep and the claims all assume this is the
                # only runner; the lease makes that so while a replacement
                # process overlaps this one (#1166).
                if self._renew_lease():
                    if not recovered:
                        self._recover(before_recovery)
                        recovered = True
                    try:
                        await self.tick()
                    except Exception as exc:  # keep the loop alive
                        logger.error("Operations runner tick failed", error=str(exc))
                try:
                    await asyncio.wait_for(
                        self._event().wait(), timeout=self._poll_interval
                    )
                except asyncio.TimeoutError:
                    pass
                self._event().clear()
        finally:
            # With tasks still running, `drain()` releases it once they end.
            self._loop_exited = True
            self._release_lease_if_idle()
        logger.info("Operations runner stopped")

    # -- lease -----------------------------------------------------------------

    def acquire_lease(self, db: Session) -> bool:
        """Take or renew the runner lease; False while another live runner
        holds it."""
        now = utc_now()
        values = {
            "holder": self._lease_holder,
            "expires_at": now + timedelta(seconds=self._lease_seconds),
        }
        taken = (
            db.query(OperationsRunnerLease)
            .filter(
                OperationsRunnerLease.id == 1,
                or_(
                    OperationsRunnerLease.holder == self._lease_holder,
                    OperationsRunnerLease.holder.is_(None),
                    OperationsRunnerLease.expires_at < now,
                ),
            )
            .update(values, synchronize_session=False)
        )
        if taken:
            db.commit()
            return True
        if db.get(OperationsRunnerLease, 1) is not None:
            db.rollback()
            return False
        db.add(OperationsRunnerLease(id=1, **values))
        try:
            db.commit()
        except IntegrityError:  # another runner inserted it first
            db.rollback()
            return False
        return True

    def release_lease(self, db: Session) -> None:
        db.query(OperationsRunnerLease).filter(
            OperationsRunnerLease.id == 1,
            OperationsRunnerLease.holder == self._lease_holder,
        ).update({"holder": None, "expires_at": None}, synchronize_session=False)
        db.commit()

    def _renew_lease(self) -> bool:
        db = self._session()
        try:
            held = self.acquire_lease(db)
        except Exception as exc:
            # a locked database: the tick would fail on it too
            db.rollback()
            logger.warning(
                "Could not renew the operations runner lease", error=str(exc)
            )
            return False
        finally:
            db.close()
        if held != self._holds_lease:
            if held:
                logger.info("Operations runner lease acquired")
            else:
                # ponytail: a runner that loses the lease (a loop stalled past
                # it) keeps the tasks it already started running
                logger.warning(
                    "Operations runner is waiting for the lease, another "
                    "process holds it"
                )
        self._holds_lease = held
        return held

    def _release_lease_if_idle(self) -> None:
        """Hand the lease over only when nothing of this runner can still
        claim or run: the loop has ended and its tasks with it."""
        if not self._loop_exited or self.running_tasks or self._drain_timed_out:
            return
        db = self._session()
        try:
            self.release_lease(db)
        except Exception as exc:  # it expires on its own
            db.rollback()
            logger.warning(
                "Could not release the operations runner lease", error=str(exc)
            )
        finally:
            db.close()
        self._holds_lease = None

    def _recover(self, before_recovery: Optional[Callable[[], None]]) -> None:
        if before_recovery is not None:
            try:
                before_recovery()
            except Exception as exc:
                logger.error("Startup sweeps failed", error=str(exc))
        try:
            db = self._session()
            try:
                self.recover_on_startup(db)
            finally:
                db.close()
        except Exception as exc:
            logger.error("Operations recovery failed", error=str(exc))

    # -- scheduling ------------------------------------------------------------

    async def record_unrecorded_outcomes(self, db: Session) -> int:
        """Write the outcome of a task of this runner whose terminal commit
        failed (a locked or unreachable database at that moment). Its row
        would otherwise stay `running` with nothing behind it until the next
        restart: an exclusive kind holds its repository's lane, and every
        `wait_for_backup_operation` on it polls forever. Only rows this
        process ran are here, so a row another process or inline
        maintenance keeps `running` is never touched; index kinds are not
        either, `requeue_abandoned_index_rows` recovers those. The write is
        the terminal write's, which the service that ran the work in its
        own session (a server backup, a maintenance service) does not
        pre-empt: the row it closed gets the task's verdict and the rest of
        what the terminal write carries, its result above all, a cancel the
        task observed included. A row already `failed` or `cancelled` keeps
        that: the service's own failure says the same, another process's
        failure (`recover_on_startup`: "interrupted by restart") is its
        diagnosis of the row, and a cancel written after the task ended (the
        backup cancel route on a row left `running`) is the newer word, as
        is the executor's own. A success still owes the chain the terminal write never
        reached, once: a follow-up chain that already hangs off the row (a
        retry after the chain's commit) is not enqueued again, while a
        plan's maintenance hanging off it is not the chain. An entry stays
        for the next tick until its row and follow-ups are both in, without
        costing the others theirs, for as long as the database is the
        problem (`TRANSIENT_DATABASE_ERRORS`). Any other error is the
        write's own: the entry gets one more try, without its result (the
        one field with content of its own) when the row has not taken it
        yet; failing that it is dropped with an error log, and the row
        stays as it is."""
        recorded = 0
        for operation_id, pending in list(self.unrecorded_outcomes.items()):
            if operation_id in self.running_tasks:
                # a new dispatch owns the row; its task writes the verdict
                del self.unrecorded_outcomes[operation_id]
                continue
            statuses = (
                {"running"}
                if pending.fallback
                else {"running", "skipped", *SUCCESS_STATUSES}
            )
            values = {
                "status": pending.status,
                "result": pending.result,
                "skip_reason": pending.skip_reason,
                "error_message": pending.error_message,
                "completed_at": pending.completed_at,
            }
            if pending.started_at is not None:
                values["started_at"] = pending.started_at
            record_committed = False
            try:
                written = (
                    db.query(Operation)
                    .filter(
                        Operation.id == operation_id,
                        Operation.kind == pending.kind,
                        Operation.repository_id == pending.repository_id,
                        Operation.run_id == pending.run_id,
                        Operation.status.in_(tuple(sorted(statuses))),
                    )
                    .update(values, synchronize_session=False)
                )
                db.commit()
                record_committed = True
                op = db.get(Operation, operation_id)
                if op is not None and op.run_id != pending.run_id:
                    op = None  # the id was handed out again; not this row
                if (
                    op is not None
                    and op.status in SUCCESS_STATUSES
                    and db.query(Operation.id)
                    .filter(
                        Operation.depends_on_id == op.id,
                        Operation.trigger == "followup",
                    )
                    .first()
                    is None
                ):
                    enqueue_followups(
                        db, op, depends_on_id=op.id, available=self._registered_kinds()
                    )
            except TRANSIENT_DATABASE_ERRORS as exc:
                db.rollback()
                logger.warning(
                    "Could not record an operation outcome yet",
                    operation_id=operation_id,
                    error=str(exc),
                )
                continue
            except Exception as exc:
                db.rollback()
                if not pending.retried:
                    pending.retried = True
                    if not record_committed:
                        pending.result = None
                    logger.warning(
                        "Could not record an operation outcome, trying once more",
                        operation_id=operation_id,
                        without_result=pending.result is None,
                        error=str(exc),
                    )
                else:
                    del self.unrecorded_outcomes[operation_id]
                    logger.error(
                        "Could not record an operation outcome; the row keeps "
                        "its status",
                        operation_id=operation_id,
                        status=pending.status,
                        error=str(exc),
                    )
                continue
            del self.unrecorded_outcomes[operation_id]
            self.cancel_requested.discard(operation_id)
            if not written or op is None:
                continue
            recorded += 1
            logger.warning(
                "Recorded an operation outcome after its terminal commit failed",
                operation_id=operation_id,
                status=pending.status,
            )
            try:
                await broadcast_operation_updated(op, db)
            except Exception as exc:  # the row is stored; the board refetches
                logger.warning(
                    "Could not broadcast a recorded operation",
                    operation_id=operation_id,
                    error=str(exc),
                )
        return recorded

    async def requeue_abandoned_index_rows(self, db: Session) -> int:
        """Index rows left `running` by a task this runner no longer has (a
        task that died before its terminal commit, or none at all). The row
        holds no lock, but it would count as running index work for its
        repository and against `index_workers` until the next restart; it
        goes back to `queued` the way `recover_on_startup` puts it, and runs
        again, after the deferral path's backoff so a transient condition
        (a locked database) does not spend the budget in seconds. Bounded:
        after `MAX_REQUEUES` the row fails instead, keeping its start time
        and progress, so a condition that kills the task every time ends in
        a visible failure rather than a listing re-run every tick. The
        caller guards the sweep: a failure in it must not cost the dispatch
        pass. Every index kind is covered, `history_index`
        included, as at startup; the other exclusive kinds are not: their
        process may still be alive, which startup checks and the tick does
        not. An entry that is not a future (a test's patched task) is left
        alone: it cannot be told apart from live work."""
        changed: list[Operation] = []
        for op in (
            db.query(Operation)
            .filter(
                Operation.status == "running",
                Operation.kind.in_(tuple(sorted(INDEX_KINDS))),
            )
            .all()
        ):
            task = self.running_tasks.get(op.id)
            if task is not None and (not asyncio.isfuture(task) or not task.done()):
                continue
            if op.id in self.cancel_requested:
                # The executor observed an accepted cancel but could not
                # commit its terminal state. Finish that cancellation rather
                # than starting the work again after the database recovers.
                op.status = "cancelled"
                op.completed_at = utc_now()
            else:
                self._recover_index_row(op)
            self.running_tasks.pop(op.id, None)
            changed.append(op)
        if not changed:
            return 0
        db.commit()
        logger.warning(
            "Swept abandoned index operations",
            requeued=sum(1 for op in changed if op.status == "queued"),
            failed=sum(1 for op in changed if op.status == "failed"),
            cancelled=sum(1 for op in changed if op.status == "cancelled"),
        )
        for op in changed:
            if op.status == "cancelled":
                self.cancel_requested.discard(op.id)
            try:
                await broadcast_operation_updated(op, db)
            except Exception as exc:  # the row is stored; the board refetches
                logger.warning(
                    "Could not broadcast a requeued operation",
                    operation_id=op.id,
                    error=str(exc),
                )
        return len(changed)

    def _recover_index_row(self, op: Operation) -> None:
        """Apply one retry budget and backoff at startup and during the tick."""
        requeues = requeue_count(op) + 1
        if requeues > MAX_REQUEUES:
            # the row keeps its start time and progress: the only
            # evidence of how far the work got
            op.status = "failed"
            op.error_message = (
                f"lost by the runner again after {MAX_REQUEUES} requeues: the "
                "operation kept ending without a result"
            )
            op.completed_at = utc_now()
        else:
            self._reset_index_row(op)
            params = op.params if isinstance(op.params, dict) else {}
            # the deferral path's gate; a row deferred a few times and then
            # swept keeps the larger of the two backoffs
            backoff = self.deferral_delay_for(max(requeues, deferral_count(op)))
            op.params = {
                **params,
                "requeues": requeues,
                "deferred_until": time.time() + backoff,
            }

    @staticmethod
    def _reset_index_row(op: Operation) -> None:
        op.status = "queued"
        op.error_message = None
        op.started_at = None
        op.process_pid = None
        op.process_start_time = None
        op.progress_percent = None
        op.progress_current = None
        op.progress_total = None
        op.progress_message = None

    async def tick(self) -> int:
        dispatched = 0
        db: Session = self._session()
        try:
            try:
                await self.record_unrecorded_outcomes(db)
            except Exception as exc:
                # housekeeping like the sweep below
                db.rollback()
                logger.warning("Recording unrecorded outcomes failed", error=str(exc))
            try:
                await self.requeue_abandoned_index_rows(db)
            except Exception as exc:
                # the sweep is housekeeping; the dispatch pass must not
                # depend on it (a locked database, an unreadable row)
                db.rollback()
                logger.warning(
                    "Sweep of abandoned index operations failed", error=str(exc)
                )
            system_settings = db.query(SystemSettings).first()
            queued = (
                db.query(Operation)
                .filter(Operation.status == "queued")
                .order_by(
                    Operation.priority.asc(),
                    Operation.created_at.asc(),
                    Operation.id.asc(),
                )
                .all()
            )
            now = time.time()
            for op in queued:
                if self._stopped:
                    # a stop during this tick's awaits; the drain after it
                    # waits only for what is already running
                    break
                if op.id in self.running_tasks:
                    continue
                not_before = deferred_until(op)
                if not_before is not None and not_before > now:
                    continue
                if op.depends_on_id is not None:
                    dependency = db.get(Operation, op.depends_on_id)
                    if (
                        dependency is None
                        or dependency.status in _FAILED_DEPENDENCY_STATUSES
                        or (
                            dependency.status == "skipped"
                            and dependency.skip_reason == "dependency_failed"
                        )
                    ):
                        await self._skip(db, op, "dependency_failed")
                        continue
                    if dependency.status not in _SATISFIED_DEPENDENCY_STATUSES:
                        continue
                if self._get_executor(op.kind) is None:
                    await self._skip(db, op, "executor_unavailable")
                    continue
                if not can_start(db, op, system_settings):
                    continue
                # Conditional claim: the candidates were loaded before the
                # awaits above, and a cancel can commit during one of them.
                # Only a row still queued is taken; otherwise it is left as
                # whoever changed it wrote it.
                claimed = (
                    db.query(Operation)
                    .filter(Operation.id == op.id, Operation.status == "queued")
                    .update(
                        {"status": "running", "started_at": utc_now()},
                        synchronize_session=False,
                    )
                )
                db.commit()
                if not claimed:
                    db.expire(op)
                    continue
                db.refresh(op)
                await broadcast_operation_updated(op, db)
                self.running_tasks[op.id] = asyncio.create_task(
                    self.run_operation(
                        op.id,
                        kind=op.kind,
                        repository_id=op.repository_id,
                        run_id=op.run_id,
                        claimed_at=op.started_at,
                    )
                )
                dispatched += 1
        finally:
            db.close()
        return dispatched

    async def _skip(self, db: Session, op: Operation, reason: str) -> None:
        op.status = "skipped"
        op.skip_reason = reason
        op.completed_at = utc_now()
        db.commit()
        await broadcast_operation_updated(op, db)

    # -- execution -------------------------------------------------------------

    async def run_operation(
        self,
        operation_id: int,
        *,
        kind: Optional[str] = None,
        repository_id: Optional[int] = None,
        run_id: Optional[str] = None,
        claimed_at: Optional[datetime] = None,
    ) -> None:
        """`kind`, `repository_id`, `run_id` and `claimed_at` are the tick's
        claim: the row is `running` because of this task from here on, even
        when its first read below fails, so the outcome bookkeeping in
        `finally` does not depend on that read."""
        db: Session = self._session()
        ctx: Optional[OperationContext] = None
        deferred = False
        terminal_committed = False
        terminal: Optional[_UnrecordedOutcome] = None
        try:
            op = db.get(Operation, operation_id)
            if op is None or op.status != "running":
                kind = None  # not this task's row
                return
            kind = op.kind
            repository_id = op.repository_id
            run_id = op.run_id
            # The start this dispatch's claim wrote. An executor that hands
            # its row to a service which claims it through `claim_running`
            # (`executors/maintenance.py`) clears it first; a service that
            # never gets that far leaves the row with no start, and the
            # terminal writes below put this one back so the run keeps its
            # place in the history and its duration.
            claimed_at = op.started_at
            executor = self._get_executor(op.kind)
            ctx = OperationContext(self, db, op)
            outcome: Optional[Outcome]
            busy_error: Optional[str] = None
            try:
                outcome = await executor(ctx)
            except asyncio.CancelledError:
                op.status = "cancelled"
                if op.started_at is None:
                    op.started_at = claimed_at
                op.completed_at = utc_now()
                terminal = self._terminal_of(op)
                db.commit()
                terminal_committed = True
                await broadcast_operation_updated(op, db)
                raise
            except Exception as exc:
                if repository_busy(exc):
                    busy_error = str(exc)
                    # a cancel that arrived while the operation was being
                    # refused wins: requeueing would drop the request in
                    # `finally`, so the refusal falls through to the
                    # cancelled path below with the admission's message
                    outcome = Outcome(error_message=busy_error)
                else:
                    logger.exception(
                        "Operation failed", operation_id=op.id, kind=op.kind
                    )
                    outcome = Outcome(
                        status="failed",
                        error_message=str(exc) or exc.__class__.__name__,
                    )
            if outcome is None:
                outcome = Outcome()
            if busy_error is not None and operation_id not in self.cancel_requested:
                deferrals = deferral_count(op) + 1
                if deferrals > MAX_DEFERRALS:
                    outcome = Outcome(
                        status="failed",
                        error_message=(
                            f"repository still busy after {MAX_DEFERRALS} attempts: "
                            f"{busy_error}"
                        ),
                    )
                else:
                    logger.info(
                        "Operation deferred, repository busy",
                        operation_id=op.id,
                        kind=op.kind,
                        deferrals=deferrals,
                    )
                    delay = self.deferral_delay_for(deferrals)
                    op.status = "queued"
                    op.started_at = None
                    op.error_message = None
                    op.params = {
                        **(op.params or {}),
                        "deferrals": deferrals,
                        "deferred_until": time.time() + delay,
                    }
                    try:
                        db.commit()
                    except Exception as exc:
                        # the row would otherwise stay `running` with no task
                        # behind it until the next restart: fail it instead
                        db.rollback()
                        logger.exception(
                            "Operation requeue failed",
                            operation_id=op.id,
                            kind=op.kind,
                        )
                        outcome = Outcome(
                            status="failed",
                            error_message=(
                                f"could not requeue the deferred operation: {exc}"
                            ),
                        )
                    else:
                        # no wake, and the tick skips the operation until
                        # deferred_until: wakes from other completions must
                        # not burn the deferrals
                        deferred = True
                        await broadcast_operation_updated(op, db)
                        return
            if op.status == "cancelled" or (
                operation_id in self.cancel_requested and outcome.status != "failed"
            ):
                op.status = "cancelled"
            else:
                op.status = outcome.status
            op.result = outcome.result
            op.skip_reason = outcome.skip_reason
            op.error_message = outcome.error_message
            if op.started_at is None:
                op.started_at = claimed_at
            op.completed_at = utc_now()
            terminal = self._terminal_of(op)
            db.commit()
            terminal_committed = True
            await broadcast_operation_updated(op, db)
            if op.status in SUCCESS_STATUSES:
                enqueue_followups(
                    db, op, depends_on_id=op.id, available=self._registered_kinds()
                )
        finally:
            if ctx is not None:
                ctx.close()
            db.close()
            self.running_tasks.pop(operation_id, None)
            if (
                kind is not None
                and run_id is not None
                and kind not in INDEX_KINDS
                and not terminal_committed
                and not deferred
            ):
                # The row stays `running` with no task behind it; the tick
                # writes what this task reached, or a failure when it ended
                # before an outcome (an error in the runner's own bookkeeping).
                self.unrecorded_outcomes[operation_id] = terminal or _UnrecordedOutcome(
                    kind=kind,
                    repository_id=repository_id,
                    run_id=run_id,
                    status="failed",
                    result=None,
                    skip_reason=None,
                    error_message="the operation ended without a recorded result",
                    started_at=claimed_at,
                    completed_at=utc_now(),
                    fallback=True,
                )
            # Recovery needs the accepted request if the terminal write
            # failed; only a committed terminal state consumes it.
            if terminal_committed:
                self.cancel_requested.discard(operation_id)
            if not deferred:
                self.wake()

    @staticmethod
    def _terminal_of(op: Operation) -> _UnrecordedOutcome:
        """Snapshot the terminal fields before their commit: a failed commit
        expires them."""
        return _UnrecordedOutcome(
            kind=op.kind,
            repository_id=op.repository_id,
            run_id=op.run_id,
            status=op.status,
            result=op.result,
            skip_reason=op.skip_reason,
            error_message=op.error_message,
            started_at=op.started_at,
            completed_at=op.completed_at,
        )

    # -- cancellation ----------------------------------------------------------

    async def request_cancel(self, operation_id: int) -> bool:
        db: Session = self._session()
        try:
            op = db.get(Operation, operation_id)
            if op is None:
                return False
            if op.status == "queued":
                op.status = "cancelled"
                op.completed_at = utc_now()
                db.commit()
                await broadcast_operation_updated(op, db)
                return True
            if op.status == "running":
                # Cooperative cancellation only reaches an executor this
                # process is running. A row left running by another worker,
                # or one recovery kept because its process is still alive,
                # has no task here to observe the flag - say so instead of
                # reporting a cancellation that will never happen.
                if operation_id not in self.running_tasks:
                    return False
                self.cancel_requested.add(operation_id)
                return True
            return False
        finally:
            db.close()

    # -- recovery --------------------------------------------------------------

    def _recover_repository_lock(self, db: Session, op: Operation) -> None:
        from app.services.repository_executor import is_agent_executor
        from app.utils.process_utils import (
            _is_remote_repository,
            break_repository_lock,
        )

        if op.repository_id is None:
            return
        repository = db.get(Repository, op.repository_id)
        if repository is None:
            return
        try:
            if is_agent_executor(repository):
                logger.warning(
                    "Interrupted managed-agent operation may still hold its lock",
                    operation_id=op.id,
                    repository_id=repository.id,
                )
                return
            if _is_remote_repository(repository, db):
                logger.warning(
                    "Interrupted remote operation may still hold its lock",
                    operation_id=op.id,
                    repository_id=repository.id,
                )
                return
            if break_repository_lock(repository):
                logger.info(
                    "Broke lock for local repository after restart",
                    operation_id=op.id,
                    repository_id=repository.id,
                )
            else:
                logger.warning(
                    "Failed to break lock for local repository after restart",
                    operation_id=op.id,
                    repository_id=repository.id,
                )
        except Exception as exc:
            logger.warning(
                "Lock recovery raised",
                operation_id=op.id,
                error=str(exc),
            )

    def recover_on_startup(self, db: Session) -> dict:
        counts = {"requeued": 0, "failed": 0, "kept": 0}
        for op in db.query(Operation).filter(Operation.status == "running").all():
            if op.kind in INDEX_KINDS:
                self._recover_index_row(op)
                counts["requeued" if op.status == "queued" else "failed"] += 1
            elif op.process_pid and is_process_alive(
                op.process_pid, int(op.process_start_time or 0)
            ):
                counts["kept"] += 1
            else:
                op.status = "failed"
                op.error_message = "interrupted by restart"
                op.completed_at = utc_now()
                counts["failed"] += 1
                # Spec 7.6: a local repository gets the lock-break attempt the
                # per-table sweep used to make; a remote one does not, because
                # the remote process may still be running.
                if is_exclusive(op.kind):
                    self._recover_repository_lock(db, op)
        db.commit()
        logger.info("Operations recovery completed", **counts)
        return counts


operation_runner = OperationRunner()
