"""Latest legacy job per repository-status cell. The status model reads
`operations` first; until phases 5 to 8 migrate backup, check, prune,
compact, and rclone sync, their history lives in the legacy tables. Deleted
in phase 9 together with `legacy_running_exclusive`."""

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import BackupJob, CheckJob, CompactJob, PruneJob, RcloneSyncJob
from app.services.operations.vocab import SUCCESS_STATUSES

_LEGACY_MODELS = {
    "backup": BackupJob,
    "check": CheckJob,
    "prune": PruneJob,
    "compact": CompactJob,
    "mirror": RcloneSyncJob,
}
_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


def latest_legacy_terminal(
    db: Session, repository_id: int, cell: str
) -> Optional[tuple[str, datetime]]:
    model = _LEGACY_MODELS.get(cell)
    if model is None:
        return None
    row = (
        db.query(model.status, model.completed_at)
        .filter(
            model.repository_id == repository_id,
            model.status.in_(_TERMINAL),
            model.completed_at.isnot(None),
        )
        .order_by(model.completed_at.desc())
        .first()
    )
    return (row.status, row.completed_at) if row else None


def latest_legacy_success_by_repository(
    db: Session, repository_ids: Iterable[int], cell: str
) -> dict[int, datetime]:
    """Newest successful legacy completion per repository, one grouped
    query for a whole page of repositories (the card's metadata row)."""
    model = _LEGACY_MODELS.get(cell)
    ids = list(repository_ids)
    if model is None or not ids:
        return {}
    rows = (
        db.query(model.repository_id, func.max(model.completed_at))
        .filter(
            model.repository_id.in_(ids),
            model.status.in_(SUCCESS_STATUSES),
            model.completed_at.isnot(None),
        )
        .group_by(model.repository_id)
        .all()
    )
    return {repository_id: completed_at for repository_id, completed_at in rows}
