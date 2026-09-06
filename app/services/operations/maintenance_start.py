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

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import Operation, Repository
from app.services.operations.enqueue import enqueue
from app.services.operations.job_facade import MAINTENANCE_KINDS

ACTIVE_STATUSES = ("queued", "running")


def active_maintenance_operation(
    db: Session, repository_id: int, kind: str
) -> Optional[Operation]:
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
) -> Optional[Operation]:
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
) -> Operation:
    """An operation the caller runs itself, right now, instead of leaving to
    the runner. Created `running` so the runner's queued-only sweep (spec 7.1)
    never picks it up a second time. The caller is responsible for the
    terminal status."""
    from app.database.models import utc_now

    operation = enqueue(
        db,
        kind,
        repository_id=repository.id,
        trigger="manual",
        params={key: value for key, value in params.items() if value is not None},
        triggered_by_user_id=user_id,
        commit=False,
    )
    operation.status = "running"
    operation.started_at = utc_now()
    db.commit()
    db.refresh(operation)
    return operation


def finish_inline_maintenance(
    db: Session, operation: Operation, *, enqueue_followups: bool = True
) -> None:
    """Give an inline operation the follow-up chain the runner would have
    enqueued for it (spec 7.4). Call after the caller has written the terminal
    status."""
    from app.services.operations.enqueue import enqueue_chain
    from app.services.operations.executors import registered_kinds
    from app.services.operations.followups import chain_for, history_enabled
    from app.services.operations.vocab import SUCCESS_STATUSES

    if not enqueue_followups or operation.status not in SUCCESS_STATUSES:
        return
    kinds = chain_for(
        operation.kind,
        available=registered_kinds(),
        history=history_enabled(db),
    )
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
