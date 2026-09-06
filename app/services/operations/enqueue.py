"""Create operations rows. The only writer of new queued operations."""

import uuid
from typing import Iterable, Optional

import structlog
from sqlalchemy.orm import Session

from app.database.models import Operation
from app.services.operations import vocab

logger = structlog.get_logger()


def new_run_id() -> str:
    return str(uuid.uuid4())


def wake_runner() -> None:
    """Nudge the runner loop. Safe to call without a running loop."""
    try:
        from app.services.operations.runner import operation_runner

        operation_runner.wake()
    except (ImportError, RuntimeError):
        # No runner in this process (tests, scripts). The runner polls anyway.
        pass


def enqueue(
    db: Session,
    kind: str,
    *,
    repository_id: Optional[int] = None,
    trigger: str = "manual",
    priority: Optional[int] = None,
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
    triggered_by_user_id: Optional[int] = None,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    params: Optional[dict] = None,
    execution_mode: Optional[str] = None,
    commit: bool = True,
) -> Operation:
    vocab.validate_kind(kind)
    vocab.validate_trigger(trigger)
    op = Operation(
        repository_id=repository_id,
        kind=kind,
        category=vocab.category_for(kind),
        status="queued",
        trigger=trigger,
        priority=vocab.priority_for_trigger(trigger) if priority is None else priority,
        run_id=run_id or new_run_id(),
        depends_on_id=depends_on_id,
        triggered_by_user_id=triggered_by_user_id,
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
        params=params,
        execution_mode=execution_mode,
    )
    db.add(op)
    if commit:
        db.commit()
        db.refresh(op)
    else:
        db.flush()
    logger.debug(
        "Enqueued operation",
        operation_id=op.id,
        kind=kind,
        repository_id=repository_id,
        trigger=trigger,
    )
    # Only nudge the runner once the row is committed. Waking on a flush
    # sends the runner to look in its own session, where an uncommitted row
    # does not exist; it would clear the event and sleep a full poll
    # interval. Callers passing commit=False wake after their own commit.
    if commit:
        wake_runner()
    return op


def enqueue_chain(
    db: Session,
    kinds: Iterable[str],
    *,
    repository_id: Optional[int],
    trigger: str,
    priority: Optional[int] = None,
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
    triggered_by_user_id: Optional[int] = None,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    commit: bool = True,
) -> list[Operation]:
    """Enqueue kinds in order, each depending on the previous one."""
    run_id = run_id or new_run_id()
    created: list[Operation] = []
    previous_id = depends_on_id
    for kind in kinds:
        op = enqueue(
            db,
            kind,
            repository_id=repository_id,
            trigger=trigger,
            priority=priority,
            run_id=run_id,
            depends_on_id=previous_id,
            triggered_by_user_id=triggered_by_user_id,
            scheduled_job_id=scheduled_job_id,
            backup_plan_run_id=backup_plan_run_id,
            commit=False,
        )
        previous_id = op.id
        created.append(op)
    if commit:
        db.commit()
        for op in created:
            db.refresh(op)
        wake_runner()
    return created


def record_import_connect(
    db: Session, repository, *, user_id: Optional[int]
) -> Operation:
    """Record a completed import_connect for an already verified repository
    and enqueue its follow-up chain (spec sections 7.4 and A.1).

    The import route verifies the repository before the row exists, so the
    connect step is recorded as already completed; the runner never runs it.
    """
    from app.database.models import utc_now
    from app.services.operations.executors import registered_kinds
    from app.services.operations.followups import chain_for, history_enabled

    # Resolve the chain before the row exists: the plan lookup behind
    # history_enabled commits the session, and a flushed import_connect row
    # committed that way would outlive a failure in the enqueue step below as
    # an orphan without its follow-ups, beyond the reach of the caller's
    # rollback.
    kinds = chain_for(
        "import_connect",
        available=registered_kinds(),
        history=history_enabled(db),
    )
    now = utc_now()
    op = Operation(
        repository_id=repository.id,
        kind="import_connect",
        category=vocab.category_for("import_connect"),
        status="completed",
        trigger="import",
        priority=vocab.priority_for_trigger("import"),
        run_id=new_run_id(),
        triggered_by_user_id=user_id,
        result={"verified": True},
        started_at=now,
        completed_at=now,
    )
    db.add(op)
    db.flush()
    if kinds:
        enqueue_chain(
            db,
            kinds,
            repository_id=repository.id,
            trigger="followup",
            run_id=op.run_id,
            depends_on_id=op.id,
            triggered_by_user_id=user_id,
            commit=False,
        )
    db.commit()
    db.refresh(op)
    wake_runner()
    return op
