"""Server-sent events for operations (spec section 9.4)."""

from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.api.events import event_manager
from app.database.models import Operation, Repository
from app.services.operations.models import serialize_operation
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()


def _jsonable(data: dict) -> dict:
    return {
        key: serialize_datetime(value) if isinstance(value, datetime) else value
        for key, value in data.items()
    }


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
        await event_manager.broadcast_event("operation.updated", data)
    except Exception as exc:
        logger.warning(
            "Failed to broadcast operation.updated",
            operation_id=op.id,
            error=str(exc),
        )


async def broadcast_operation_progress(op: Operation) -> None:
    data = {
        "id": op.id,
        "progress_percent": op.progress_percent,
        "progress_current": op.progress_current,
        "progress_total": op.progress_total,
        "progress_message": op.progress_message,
    }
    try:
        await event_manager.broadcast_event("operation.progress", data)
    except Exception as exc:
        logger.warning(
            "Failed to broadcast operation.progress",
            operation_id=op.id,
            error=str(exc),
        )
