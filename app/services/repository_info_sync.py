"""Write archive stats back to the repository row from a fresh `info` listing.

The repository card renders the stored archive_count/last_backup columns, they
are written by the stats refresh and, in part, by backup completion. The info
dialog fetches the authoritative archive list moments later and used to throw
it away, so a backup finishing between a stats refresh and the info click left
the dialog showing two archives while the card still said one. When the info
entries carry ids the sync now also upserts the archives table (spec 6.4) and
derives the columns from it; when they do not, it falls back to writing the
columns directly from the listing.

Borg 2 only: Borg 1's repository-level `info --json` carries no archive list,
so the parsed shape yields [] even for a populated repository, and writing that
back would wipe a real count to 0, the same trap the stats refresh guards
against with its list_ok check.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from app.database.models import Repository
from app.utils.datetime_utils import parse_borg_archive_time

logger = structlog.get_logger()


def _newest_archive_time(
    archives: list, *, timezone_name: Optional[str] = None
) -> Optional[datetime]:
    """The newest archive timestamp as a naive UTC value, matching the column.

    Naive Borg times are the creating machine's local wall clock; see
    parse_borg_archive_time for how ``timezone_name`` resolves them.
    """
    newest = None
    for archive in archives:
        if not isinstance(archive, dict):
            continue
        # The shared parser handles every shape borg may emit (ISO strings
        # with or without offset, Unix epochs) and returns None for junk.
        # Select on None, not truthiness - the epoch 0 is a valid time.
        value = archive.get("time")
        if value is None:
            value = archive.get("start")
        dt = parse_borg_archive_time(value, timezone_name=timezone_name)
        if dt is None:
            continue
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
        # Local import: repository_executor pulls in the admission machinery,
        # which must not become an import-time dependency of this module.
        from app.services.repository_executor import agent_timezone_for_repository

        timezone_name = agent_timezone_for_repository(db, repository)
        # Full entries only: apply_listing skips one it cannot map and reports
        # the archive behind it as removed, which would drop archive_count and
        # stale last_backup on a partial listing. The check is the mapper
        # itself, so the two can never drift apart.
        from app.services.operations.executors.index import (
            apply_listing,
            archive_fields_from_listing,
            write_repository_archive_columns,
        )

        complete = bool(archives) and all(
            isinstance(a, dict)
            and archive_fields_from_listing(
                a, repository.borg_version or 2, timezone_name=timezone_name
            )
            is not None
            for a in archives
        )
        if complete:
            # Keep the archives table in step with what the dialog just showed,
            # then derive the columns from it.
            _, removed = apply_listing(
                db, repository, archives, timezone_name=timezone_name
            )
            write_repository_archive_columns(db, repository, exclude_ids=removed)
            return
        repository.archive_count = len(archives)
        newest = _newest_archive_time(archives, timezone_name=timezone_name)
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
