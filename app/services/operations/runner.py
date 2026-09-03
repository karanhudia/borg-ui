"""The operations runner (spec section 7): loop, lanes, dispatch, follow-ups,
cancellation, and crash recovery. One instance per process."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database.models import Operation, SystemSettings, utc_now
from app.services.operations import executors as executor_registry
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.events import (
    broadcast_operation_progress,
    broadcast_operation_updated,
)
from app.services.operations.followups import chain_for
from app.services.operations.lanes import can_start
from app.services.operations.vocab import INDEX_KINDS, SUCCESS_STATUSES
from app.utils.process_utils import is_process_alive

logger = structlog.get_logger()

_FAILED_DEPENDENCY_STATUSES = ("failed", "cancelled", "skipped")
_OUTCOME_STATUSES = ("completed", "completed_with_warnings", "skipped", "failed")


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
    return Path(app_settings.data_dir) / "logs" / f"operation_{operation_id}.log"


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
        self, *, session_factory=None, registry=None, poll_interval: float = 5.0
    ):
        self._session_factory = session_factory
        self._registry = (
            registry if registry is not None else executor_registry.REGISTRY
        )
        self._poll_interval = poll_interval
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
        Call `stop()` first so no new tasks start while draining."""
        tasks = list(self.running_tasks.values())
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
            for op in queued:
                if op.id in self.running_tasks:
                    continue
                if op.depends_on_id is not None:
                    dependency = db.get(Operation, op.depends_on_id)
                    if (
                        dependency is None
                        or dependency.status in _FAILED_DEPENDENCY_STATUSES
                    ):
                        await self._skip(db, op, "dependency_failed")
                        continue
                    if dependency.status not in SUCCESS_STATUSES:
                        continue
                if self._get_executor(op.kind) is None:
                    await self._skip(db, op, "executor_unavailable")
                    continue
                if not can_start(db, op, system_settings):
                    continue
                op.status = "running"
                op.started_at = utc_now()
                db.commit()
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
        try:
            op = db.get(Operation, operation_id)
            if op is None or op.status != "running":
                return
            executor = self._get_executor(op.kind)
            ctx = OperationContext(self, db, op)
            outcome: Optional[Outcome]
            try:
                outcome = await executor(ctx)
            except asyncio.CancelledError:
                op.status = "cancelled"
                op.completed_at = utc_now()
                db.commit()
                await broadcast_operation_updated(op, db)
                raise
            except Exception as exc:
                logger.exception("Operation failed", operation_id=op.id, kind=op.kind)
                outcome = Outcome(
                    status="failed",
                    error_message=str(exc) or exc.__class__.__name__,
                )
            if outcome is None:
                outcome = Outcome()
            if operation_id in self.cancel_requested and outcome.status != "failed":
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
                kinds = chain_for(op.kind, available=self._registered_kinds())
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
                self.cancel_requested.add(operation_id)
                return True
            return False
        finally:
            db.close()

    # -- recovery --------------------------------------------------------------

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
        db.commit()
        logger.info("Operations recovery completed", **counts)
        return counts


operation_runner = OperationRunner()
