"""The one way a maintenance kind starts (spec 7.1, 7.2 and section 13
phase 5).

Before this phase each route created its own job row and dispatched a task
straight away, so a second kind arriving during a backup was rejected with a
409. Now the route only enqueues; the runner starts the work when the
repository's lane is free. The single rejection left is the duplicate: asking
for a check while a check is already queued or running still answers 409, so
the button keeps behaving as users expect.
"""

from typing import Any, Optional

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import Operation, Repository
from app.services.operations.enqueue import enqueue
from app.services.operations.job_facade import MAINTENANCE_KINDS

logger = structlog.get_logger()

ACTIVE_STATUSES = ("queued", "running")


def active_maintenance_operation(db: Session, repository_id: int, kind: str) -> Any:
    """The active `Operation` for this repository and kind, if one exists."""
    return (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == kind,
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Operation.id.desc())
        .first()
    )


def start_maintenance(
    db: Session,
    repository: Repository,
    kind: str,
    *,
    trigger: str,
    params: dict[str, Any],
    user_id: Optional[int],
    duplicate_error_key: str,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
) -> Operation:
    if kind not in MAINTENANCE_KINDS:
        raise ValueError(f"Not a maintenance kind: {kind!r}")
    if active_maintenance_operation(db, repository.id, kind) is not None:
        raise HTTPException(status_code=409, detail={"key": duplicate_error_key})
    # None means "not supplied"; storing it would shadow a service default.
    stored = {key: value for key, value in params.items() if value is not None}
    return enqueue(
        db,
        kind,
        repository_id=repository.id,
        trigger=trigger,
        params=stored,
        triggered_by_user_id=user_id,
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
    )


def active_delete_for_archive(
    db: Session, repository_id: int, archive_name: str
) -> Any:
    """Deletes are rejected per archive, not per repository: two different
    archives may be removed at once, the same one may not."""
    candidates = (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "delete_archive",
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .all()
    )
    for candidate in candidates:
        if (candidate.params or {}).get("archive_name") == archive_name:
            return candidate
    return None


def start_inline_maintenance(
    db: Session,
    repository: Repository,
    kind: str,
    *,
    params: dict[str, Any],
    user_id: Optional[int],
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
) -> Operation:
    """An operation the caller runs itself, right now, instead of leaving to
    the runner. Created `running` so the runner's queued-only sweep (spec 7.1)
    never picks it up a second time, with no `started_at`: that is the shape
    `claim_running` recognises as a manual start, and the Borg 2 services
    claim the row through it before they run (a row that already carries a
    start is not theirs to claim, and they return without running). The
    caller is responsible for the terminal status.

    Post-backup maintenance passes the backup's `run_id` and id so the child
    is the backup's child in the run (spec 6.3: `running_prune` is `running`
    on the child prune operation while the backup itself is completed)."""
    from app.services.repository_executor import is_agent_executor

    operation = enqueue(
        db,
        kind,
        repository_id=repository.id,
        trigger="manual",
        params={key: value for key, value in params.items() if value is not None},
        triggered_by_user_id=user_id,
        run_id=run_id,
        depends_on_id=depends_on_id,
        # Recorded on the row so a later reader (the runtime reaper) judges
        # the operation by the executor it ran under, not by what the
        # repository is set to by then.
        execution_mode="agent" if is_agent_executor(repository) else "server",
        commit=False,
    )
    operation.status = "running"
    db.commit()
    db.refresh(operation)
    return operation


def detail_text(detail: Any) -> str:
    """An HTTPException detail as one line: its message or key, as the other
    detail flatteners do, except that the admission's generic "repository
    busy" key says which operation holds the repository instead."""
    from app.services.job_admission import REPOSITORY_OPERATION_ACTIVE_KEY

    if isinstance(detail, dict):
        message = detail.get("message")
        if message:
            return str(message)
        key = detail.get("key")
        params = detail.get("params")
        active = params.get("active_operation") if isinstance(params, dict) else None
        if key == REPOSITORY_OPERATION_ACTIVE_KEY and active:
            return f"{active} is active on the repository"
        if key:
            return str(key)
    return str(detail)


def failure_text(error: BaseException) -> str:
    """An exception as one line safe to store on a row users read. A
    SQLAlchemy statement error renders the statement and its parameters in
    `str()`, and the agent job insert carries the repository secrets, so
    only the driver's own error is kept; an HTTPException reads as its
    detail."""
    from sqlalchemy.exc import StatementError

    if isinstance(error, HTTPException):
        return detail_text(error.detail)
    if isinstance(error, StatementError):
        orig = error.orig
        if orig is not None:
            return f"{type(orig).__name__}: {orig}"
        return type(error).__name__
    return str(error) or type(error).__name__


async def fail_inline_maintenance(
    db: Session, operation: Operation, error: BaseException
) -> bool:
    """Close an inline operation whose caller raised instead of writing the
    terminal status, and say whether it did.

    A row that already reached a terminal status (the agent path fails it
    itself when its job is refused) is kept as written. So is a row a live
    agent job is still carrying: the caller's wait may have given up on a
    long prune the agent is still running, and the agent's report will
    close the row; failing it here would free the repository for the next
    step while that prune still holds it. A queued agent job counts too:
    admission holds the repository for it on its own, the agent runs it on
    its next hello, and the row must say so rather than contradict the job.
    Any other row would stay `running` with nothing behind it and block the
    repository via admission control until the next restart.

    Rolls the session back first, since the failure that got the caller
    here may have left its transaction unusable, and commits through the
    lock-retrying helper, since a locked database is one of those failures;
    call it before writing anything else on that session.
    """
    from sqlalchemy import func

    from app.database.models import utc_now
    from app.services.operations.events import broadcast_operation_updated
    from app.utils.db_retries import commit_with_retry
    from app.utils.process_utils import has_active_agent_job_for

    operation_id = kind = None
    closed = 0

    def close():
        # A guarded UPDATE rather than attribute writes: it is re-issued on
        # every retry (a rollback discards attribute writes), and a report
        # that reached the row first keeps its own verdict.
        nonlocal closed
        closed = (
            db.query(Operation)
            .filter(Operation.id == operation_id, Operation.status == "running")
            .update(
                {
                    Operation.status: "failed",
                    # a diagnostic the service recorded before raising is
                    # more specific than the exception that wrapped it
                    Operation.error_message: func.coalesce(
                        Operation.error_message, failure_text(error)
                    ),
                    Operation.completed_at: utc_now(),
                },
                synchronize_session=False,
            )
        )

    try:
        # First thing: the failure that got the caller here may have left the
        # transaction unusable, and even reading the row's id would raise.
        db.rollback()
        operation_id, kind = operation.id, operation.kind
        db.refresh(operation)
        # Same condition as the UPDATE's guard below: only the `running` row
        # an inline caller created is ours to close.
        if operation.status != "running":
            return False
        if has_active_agent_job_for(db, kind, operation_id):
            return False
        await commit_with_retry(
            db,
            prepare=close,
            logger=logger,
            action="fail_inline_maintenance",
            operation_id=operation_id,
        )
        if closed:
            db.refresh(operation)
            await broadcast_operation_updated(operation, db)
        return bool(closed)
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Could not close the inline operation after a failure",
            operation_id=operation_id,
            kind=kind,
            error=failure_text(exc),
        )
        return False


def finish_inline_maintenance(
    db: Session, operation: Operation, *, enqueue_followups: bool = True
) -> None:
    """Give an inline operation the follow-up chain the runner would have
    enqueued for it (spec 7.4). Call after the caller has written the terminal
    status."""
    from app.database.models import utc_now
    from app.services.operations.enqueue import enqueue_chain
    from app.services.operations.followups import chain_for_repository
    from app.services.operations.vocab import SUCCESS_STATUSES, TERMINAL_STATUSES

    if operation.status not in TERMINAL_STATUSES:
        # The service returned without recording a verdict, which is a bug
        # in the service (the runner's maintenance executor makes the same
        # call). Left `running`, the row would block the repository via
        # admission control until the next restart. Guarded, so a report
        # that reaches the row in the meantime keeps its verdict; and
        # nothing here may raise past the caller, or the row stays as it is.
        try:
            db.query(Operation).filter(
                Operation.id == operation.id,
                Operation.status.notin_(TERMINAL_STATUSES),
            ).update(
                {
                    Operation.status: "failed",
                    Operation.error_message: (
                        "the service returned without recording a verdict"
                    ),
                    Operation.completed_at: utc_now(),
                },
                synchronize_session=False,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Could not close the inline operation that returned no verdict",
                operation_id=operation.id,
                kind=operation.kind,
                error=failure_text(exc),
            )
            return
        db.refresh(operation)
        logger.warning(
            "Inline operation returned without a verdict",
            operation_id=operation.id,
            kind=operation.kind,
            status=operation.status,
        )
        return
    if not enqueue_followups or operation.status not in SUCCESS_STATUSES:
        return
    kinds = chain_for_repository(db, operation.kind, operation.repository_id)
    if not kinds:
        return
    enqueue_chain(
        db,
        kinds,
        repository_id=operation.repository_id,
        trigger="followup",
        run_id=operation.run_id,
        depends_on_id=operation.id,
        triggered_by_user_id=operation.triggered_by_user_id,
    )
