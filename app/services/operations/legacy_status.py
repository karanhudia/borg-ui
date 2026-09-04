"""Latest terminal legacy job per status-strip cell. The strip reads
`operations` first; until phases 5 to 8 migrate backup, check, prune,
compact, and rclone sync, their history lives in the legacy tables. Deleted
in phase 9 together with `legacy_running_exclusive`."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import BackupJob, CheckJob, CompactJob, PruneJob, RcloneSyncJob

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
