"""Write archive stats back to the repository row from a fresh `info` listing.

The repository card renders the stored archive_count/last_backup columns; they
are written by the stats refresh and, in part, by backup completion. The info
dialog fetches the authoritative archive list moments later and used to throw
it away — so a backup finishing between a stats refresh and the info click left
the dialog showing two archives while the card still said one.

Borg 2 only: Borg 1's repository-level `info --json` carries no archive list,
so the parsed shape yields [] even for a populated repository, and writing that
back would wipe a real count to 0 — the same trap the stats refresh guards
against with its list_ok check.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

from app.database.models import Repository

logger = structlog.get_logger()


def _newest_archive_time(archives: list) -> Optional[datetime]:
    """The newest archive timestamp as a naive UTC value, matching the column."""
    newest = None
    for archive in archives:
        if not isinstance(archive, dict):
            continue
        value = archive.get("time") or archive.get("start")
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        if newest is None or dt > newest:
            newest = dt
    return newest


def sync_archive_stats_from_info(
    repository: Repository, info_data: Dict[str, Any], db
) -> None:
    """Best-effort by design: the info response has already been served either
    way, so a failed write is logged, never raised."""
    if repository.borg_version != 2:
        return
    archives = info_data.get("archives")
    if not isinstance(archives, list):
        return
    # Captured before the commit/rollback below: a rollback expires ORM
    # attributes, so reading repository.name afterwards could itself hit the
    # database and raise — inside the handler that promises never to.
    repository_name = repository.name
    try:
        repository.archive_count = len(archives)
        newest = _newest_archive_time(archives)
        if archives:
            # Archives whose times we cannot parse must not wipe a known
            # last_backup — absence of evidence only counts when the list
            # itself is empty.
            if newest:
                repository.last_backup = newest
        else:
            repository.last_backup = None
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception as rollback_error:
            # Still best-effort: a session too broken to roll back must not
            # take the already-served info response down with it.
            logger.warning(
                "rollback after failed archive stats sync failed",
                repository=repository_name,
                error=str(rollback_error),
            )
        logger.warning(
            "archive stats sync from info failed",
            repository=repository_name,
            error=str(e),
        )
