"""The operations runner (spec section 7): loop, lanes, dispatch, follow-ups,
cancellation, and crash recovery. One instance per process."""

import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy.orm import Session

import app.config as app_config
from app.database.models import Operation, Repository, SystemSettings, utc_now
from app.services.operations import executors as executor_registry
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.events import (
    broadcast_operation_progress,
    broadcast_operation_updated,
)
from app.services.operations.followups import chain_for_repository
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
# Each deferral waits before the next attempt, doubling from 5 s to 5 min.
# The runner is woken by every completion anywhere in the system, so without
# the delay a busy install would spend the whole deferral budget in seconds
# while a pending prune sits on the repository. 20 attempts give a
# repository about 75 minutes to free up.
DEFERRAL_DELAY_SECONDS = 5.0
DEFERRAL_MAX_DELAY_SECONDS = 300.0
REPOSITORY_BUSY_KEY = "backend.errors.jobs.repositoryOperationActive"


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


def repository_busy(exc: BaseException) -> bool:
    """True for the admission's 409 (repositoryOperationActive)."""
    if getattr(exc, "status_code", None) != 409:
        return False
    detail = getattr(exc, "detail", None)
    return isinstance(detail, dict) and detail.get("key") == REPOSITORY_BUSY_KEY


@dataclass
class Outcome:
    status: str = "completed"
    result: Optional[dict] = None
    skip_reason: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.status not in _OUTCOME_STATUSES:
            raise ValueError(f"Invalid outcome status: {self.status!r}")


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
    ):
        self._session_factory = session_factory
        self._registry = (
            registry if registry is not None else executor_registry.REGISTRY
        )
        self._poll_interval = poll_interval
        self._deferral_delay = deferral_delay
        self._wake: Optional[asyncio.Event] = None
        self._stopped = False
        self.running_tasks: dict[int, asyncio.Task] = {}
        self.cancel_requested: set[int] = set()

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

    async def start(self) -> None:
        self._stopped = False
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
        logger.info("Operations runner started", poll_interval=self._poll_interval)
        while not self._stopped:
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
        logger.info("Operations runner stopped")

    # -- scheduling ------------------------------------------------------------

    async def tick(self) -> int:
        dispatched = 0
        db: Session = self._session()
        try:
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
                    self.run_operation(op.id)
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

    async def run_operation(self, operation_id: int) -> None:
        db: Session = self._session()
        ctx: Optional[OperationContext] = None
        deferred = False
        try:
            op = db.get(Operation, operation_id)
            if op is None or op.status != "running":
                return
            executor = self._get_executor(op.kind)
            ctx = OperationContext(self, db, op)
            outcome: Optional[Outcome]
            busy_error: Optional[str] = None
            try:
                outcome = await executor(ctx)
            except asyncio.CancelledError:
                op.status = "cancelled"
                op.completed_at = utc_now()
                db.commit()
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
                        await broadcast_operation_updated(op, db)
                        # no wake, and the tick skips the operation until
                        # deferred_until: wakes from other completions must
                        # not burn the deferrals
                        deferred = True
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
            op.completed_at = utc_now()
            db.commit()
            await broadcast_operation_updated(op, db)
            if op.status in SUCCESS_STATUSES:
                kinds = chain_for_repository(
                    db,
                    op.kind,
                    op.repository_id,
                    available=self._registered_kinds(),
                )
                if kinds:
                    enqueue_chain(
                        db,
                        kinds,
                        repository_id=op.repository_id,
                        trigger="followup",
                        run_id=op.run_id,
                        depends_on_id=op.id,
                        triggered_by_user_id=op.triggered_by_user_id,
                        scheduled_job_id=op.scheduled_job_id,
                        backup_plan_run_id=op.backup_plan_run_id,
                    )
        finally:
            if ctx is not None:
                ctx.close()
            db.close()
            self.running_tasks.pop(operation_id, None)
            self.cancel_requested.discard(operation_id)
            if not deferred:
                self.wake()

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
                op.status = "queued"
                op.started_at = None
                op.process_pid = None
                op.process_start_time = None
                op.progress_percent = None
                op.progress_current = None
                op.progress_total = None
                op.progress_message = None
                counts["requeued"] += 1
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
