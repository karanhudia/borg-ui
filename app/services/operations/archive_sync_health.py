"""Persistent archive-listing failures for repository cards, batched per page."""

from collections import defaultdict
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import Operation, Repository
from app.services.operations.index_mode import mode_of
from app.services.operations.vocab import SUCCESS_STATUSES
from app.utils.datetime_utils import serialize_datetime
from app.utils.redaction import redact_secrets


def archive_sync_warnings(
    db: Session, repositories: Iterable[Repository]
) -> dict[int, dict]:
    """Warn after two failed terminal attempts; success clears the warning.

    Queued/running retries and canceled/skipped work do not replace the last
    verdict. Rank by completion time so an older queued job finishing later
    still supplies the newest verdict. Two bounded queries serve the page.
    """
    ids = [repo.id for repo in repositories if mode_of(repo) != "off"]
    if not ids:
        return {}
    ranked = (
        db.query(
            Operation.repository_id,
            Operation.id,
            Operation.status,
            Operation.error_message,
            func.row_number()
            .over(
                partition_by=Operation.repository_id,
                order_by=(Operation.completed_at.desc(), Operation.id.desc()),
            )
            .label("rank"),
        )
        .filter(
            Operation.repository_id.in_(ids),
            Operation.kind == "archive_sync",
            Operation.status.in_((*SUCCESS_STATUSES, "failed")),
            Operation.completed_at.isnot(None),
        )
        .subquery()
    )
    attempts = defaultdict(list)
    for row in db.query(ranked).filter(ranked.c.rank <= 2).order_by(ranked.c.rank):
        attempts[row.repository_id].append(row)
    failed = {
        repo_id: rows[0]
        for repo_id, rows in attempts.items()
        if len(rows) == 2 and all(row.status == "failed" for row in rows)
    }
    if not failed:
        return {}
    successes = dict(
        db.query(Operation.repository_id, func.max(Operation.completed_at))
        .filter(
            Operation.repository_id.in_(failed),
            Operation.kind == "archive_sync",
            Operation.status.in_(SUCCESS_STATUSES),
        )
        .group_by(Operation.repository_id)
        .all()
    )
    return {
        repo_id: {
            "operation_id": row.id,
            "error_message": redact_secrets(row.error_message or "")[:2000],
            "last_success_at": serialize_datetime(successes.get(repo_id)),
        }
        for repo_id, row in failed.items()
    }
