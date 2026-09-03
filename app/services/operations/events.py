"""Server-sent events for operations (spec section 9.4)."""

from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.api.events import event_manager
from app.core.security import check_repo_access
from app.database.models import Operation, Repository, User
from app.services.operations.models import serialize_operation
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()


def _jsonable(data: dict) -> dict:
    return {
        key: serialize_datetime(value) if isinstance(value, datetime) else value
        for key, value in data.items()
    }


async def _broadcast_scoped(
    event_type: str, data: dict, db: Optional[Session], repository_id: Optional[int]
) -> None:
    """Deliver to every connection when the row has no repository (system
    kinds), otherwise only to users with viewer access to that repository."""
    if db is None or repository_id is None:
        await event_manager.broadcast_event(event_type, data)
        return
    repository = db.get(Repository, repository_id)
    if repository is None:
        return
    for user_id in list(event_manager.connections.keys()):
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            continue
        user = db.get(User, uid)
        if user is None:
            continue
        try:
            check_repo_access(db, user, repository, "viewer")
        except Exception:
            continue
        await event_manager.broadcast_event(event_type, data, user_id=user_id)


async def broadcast_operation_updated(
    op: Operation, db: Optional[Session] = None
) -> None:
    repository_name = None
    repository_path = None
    if db is not None and op.repository_id is not None:
        repository = db.get(Repository, op.repository_id)
        if repository is not None:
            repository_name = repository.name
            repository_path = repository.path
    data = _jsonable(
        serialize_operation(
            op, repository_name=repository_name, repository_path=repository_path
        )
    )
    try:
        await _broadcast_scoped("operation.updated", data, db, op.repository_id)
    except Exception as exc:
        logger.warning(
            "Failed to broadcast operation.updated",
            operation_id=op.id,
            error=str(exc),
        )


async def broadcast_operation_progress(
    op: Operation, db: Optional[Session] = None
) -> None:
    data = {
        "id": op.id,
        "progress_percent": op.progress_percent,
        "progress_current": op.progress_current,
        "progress_total": op.progress_total,
        "progress_message": op.progress_message,
    }
    try:
        await _broadcast_scoped("operation.progress", data, db, op.repository_id)
    except Exception as exc:
        logger.warning(
            "Failed to broadcast operation.progress",
            operation_id=op.id,
            error=str(exc),
        )
