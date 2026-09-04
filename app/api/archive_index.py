"""Database-backed archive routes (spec section 9.2): list, detail,
heatmap, status strip, rebuild, and (Pro) changes, history, search."""

from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.maintenance_jobs import get_repository_with_access
from app.core.features import require_feature, require_feature_access
from app.core.security import get_current_user
from app.database.database import get_db
from app.database.models import (
    Archive,
    ArchiveChange,
    Operation,
    Repository,
    SystemSettings,
    User,
    utc_now,
)
from app.services.operations import anomalies
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.executors.history import predecessor_of, successor_of
from app.services.operations.followups import HISTORY_KINDS, history_enabled
from app.services.operations.history_fold import Change, fold_sequence, rows_to_changes
from app.services.operations.legacy_status import latest_legacy_terminal
from app.services.operations.series import cron_for_repository
from app.services.operations.vocab import PRIORITY_RECONCILE

router = APIRouter()

NOT_FOUND = {"key": "backend.errors.archives.notFound"}
STALE_AFTER_INTERVALS = 2
STRIP_CELLS: tuple[tuple[str, dict], ...] = (
    ("backup", {"kinds": ("backup",)}),
    ("check", {"kinds": ("check",)}),
    ("prune", {"kinds": ("prune",)}),
    ("compact", {"kinds": ("compact",)}),
    ("index", {"category": "index"}),
    ("mirror", {"category": "mirror"}),
)


def _repo(db: Session, user: User, repo_id: int, role: str = "viewer") -> Repository:
    return get_repository_with_access(db, user, repo_id, required_role=role)


def serialize_archive(a: Archive) -> dict:
    return {
        "id": a.id,
        "repository_id": a.repository_id,
        "borg_id": a.borg_id,
        "name": a.name,
        "series": a.series,
        "start": a.start,
        "end": a.end,
        "duration_seconds": a.duration_seconds,
        "nfiles": a.nfiles,
        "original_size": a.original_size,
        "compressed_size": a.compressed_size,
        "deduplicated_size": a.deduplicated_size,
        "hostname": a.hostname,
        "username": a.username,
        "comment": a.comment,
        "backup_operation_id": a.backup_operation_id,
        "history_state": a.history_state,
        "history_indexed_at": a.history_indexed_at,
        "history_rows": a.history_rows,
        "history_truncated": a.history_truncated,
        "first_seen_at": a.first_seen_at,
        "last_seen_at": a.last_seen_at,
    }


def sync_state_for(
    db: Session, repository: Repository
) -> tuple[str, Optional[datetime]]:
    active = (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "archive_sync",
            Operation.status.in_(("queued", "running")),
        )
        .first()
    )
    last = (
        db.query(Operation.completed_at)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "archive_sync",
            Operation.status.in_(("completed", "completed_with_warnings")),
        )
        .order_by(Operation.completed_at.desc())
        .first()
    )
    last_at = last.completed_at if last else None
    if active:
        return "syncing", last_at
    if last_at is None:
        return "never", None
    settings = db.query(SystemSettings).first()
    interval = (settings.stats_refresh_interval_minutes if settings else None) or 60
    # DB timestamps round-trip as naive UTC (spec 6.1); compare against a
    # naive "now" rather than utc_now()'s tz-aware value.
    if utc_now().replace(tzinfo=None) - last_at > timedelta(
        minutes=interval * STALE_AFTER_INTERVALS
    ):
        return "stale", last_at
    return "fresh", last_at


def _archives_query(db: Session, repository: Repository, series, since, until):
    q = db.query(Archive).filter(Archive.repository_id == repository.id)
    if series:
        q = q.filter(Archive.series == series)
    if since:
        q = q.filter(Archive.start >= since)
    if until:
        q = q.filter(Archive.start <= until)
    return q


@router.get("/{repo_id}/archives")
async def list_archives(
    repo_id: int,
    series: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    rows = (
        _archives_query(db, repository, series, since, until)
        .order_by(Archive.start.desc(), Archive.id.desc())
        .all()
    )
    all_series = [
        s
        for (s,) in db.query(Archive.series)
        .filter(Archive.repository_id == repository.id)
        .distinct()
        .all()
    ]
    state, last_at = sync_state_for(db, repository)
    return {
        "archives": [serialize_archive(a) for a in rows],
        "series": all_series,
        "sync_state": state,
        "last_synced_at": last_at,
        "history_available": history_enabled(db),
    }


@router.get("/{repo_id}/archives/heatmap")
async def archives_heatmap(
    repo_id: int,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    until = until or utc_now().replace(tzinfo=None)
    since = since or until - timedelta(days=365)
    pro = history_enabled(db)
    rows = (
        _archives_query(db, repository, None, since, until)
        .order_by(Archive.series.asc(), Archive.start.asc())
        .all()
    )
    cron_expression, timezone_name = cron_for_repository(db, repository)
    by_series: dict[str, list[Archive]] = {}
    for a in rows:
        by_series.setdefault(a.series, []).append(a)
    out = []
    for name, archives in by_series.items():
        flags = (
            anomalies.series_flags(archives) if pro else {a.id: [] for a in archives}
        )
        days: dict[str, dict] = {}
        for a in archives:
            key = a.start.date().isoformat()
            day = days.setdefault(
                key,
                {
                    "date": key,
                    "count": 0,
                    "deduplicated_size": 0,
                    "duration_seconds": 0.0,
                    "archive_ids": [],
                    "anomalies": [],
                },
            )
            day["count"] += 1
            day["deduplicated_size"] += a.deduplicated_size or 0
            day["duration_seconds"] += a.duration_seconds or 0.0
            day["archive_ids"].append(a.id)
            for flag in flags.get(a.id, []):
                if flag not in day["anomalies"]:
                    day["anomalies"].append(flag)
        missed = anomalies.missed_run_days(
            [a.start for a in archives],
            until=until,
            cron_expression=cron_expression,
            timezone_name=timezone_name,
        )
        out.append(
            {
                "series": name,
                "days": list(days.values()),
                "missed_days": sorted(d.isoformat() for d in missed),
                "first": archives[0].start,
                "last": archives[-1].start,
            }
        )
    return {
        "since": since,
        "until": until,
        "series": out,
        "flags_available": {
            "missed_run": True,
            "size_outlier": pro,
            "duration_outlier": pro,
        },
    }


def _archive_or_404(db: Session, repository: Repository, archive_id: int) -> Archive:
    archive = db.get(Archive, archive_id)
    if archive is None or archive.repository_id != repository.id:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return archive


@router.get("/{repo_id}/archives/{archive_id}")
async def get_archive(
    repo_id: int,
    archive_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    archive = _archive_or_404(db, repository, archive_id)
    predecessor = predecessor_of(db, archive)
    successor = successor_of(db, archive)
    return {
        **serialize_archive(archive),
        "predecessor_id": predecessor.id if predecessor else None,
        "successor_id": successor.id if successor else None,
        "history_available": history_enabled(db),
    }


@router.get("/{repo_id}/status-strip")
async def status_strip(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    pro = history_enabled(db)
    now = utc_now().replace(tzinfo=None)
    # `repository_type` is the persisted rclone/mirror marker (spec 6.4);
    # `cloud_mirror_enabled` is only a create-time request field, not a
    # Repository column.
    mirror_applies = repository.repository_type == "rclone"
    cells = []
    for cell, spec in STRIP_CELLS:
        if cell == "mirror" and not mirror_applies:
            continue
        q = db.query(Operation).filter(Operation.repository_id == repository.id)
        if "kinds" in spec:
            q = q.filter(Operation.kind.in_(spec["kinds"]))
        else:
            q = q.filter(Operation.category == spec["category"])
        running = q.filter(Operation.status == "running").first() is not None
        latest = (
            q.filter(
                Operation.status.in_(
                    ("completed", "completed_with_warnings", "failed", "cancelled")
                )
            )
            .order_by(Operation.completed_at.desc())
            .first()
        )
        status, completed_at, source = (
            (latest.status, latest.completed_at, "operations")
            if latest
            else (None, None, None)
        )
        legacy = latest_legacy_terminal(db, repository.id, cell)
        if legacy and (completed_at is None or legacy[1] > completed_at):
            status, completed_at, source = legacy[0], legacy[1], "legacy"
        cells.append(
            {
                "cell": cell,
                "status": status,
                "completed_at": completed_at,
                "age_seconds": (now - completed_at).total_seconds()
                if completed_at
                else None,
                "threshold_days": anomalies.OVERDUE_THRESHOLD_DAYS[cell],
                "overdue": anomalies.overdue(cell, completed_at, now) if pro else None,
                "running": running,
                "source": source,
            }
        )
    return {"cells": cells, "overdue_available": pro}


class RebuildRequest(BaseModel):
    from_stage: Literal["stats", "archives", "history"] = Field(alias="from")

    model_config = {"populate_by_name": True}


@router.post("/{repo_id}/rebuild")
async def rebuild(
    repo_id: int,
    body: RebuildRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invalidate a derived-data stage and the stages after it, then enqueue
    a manual run at priority 20 (spec 9.2)."""
    repository = _repo(db, current_user, repo_id, role="operator")
    history = history_enabled(db)
    if body.from_stage == "history":
        require_feature_access(db, "archive_history")
    archives = db.query(Archive).filter(Archive.repository_id == repository.id).all()
    if body.from_stage == "archives":
        for a in archives:
            a.original_size = None
        kinds = ["archive_sync", "history_index", "stats"]
    elif body.from_stage == "history":
        ids = [a.id for a in archives]
        if ids:
            db.query(ArchiveChange).filter(ArchiveChange.archive_id.in_(ids)).delete(
                synchronize_session=False
            )
        for a in archives:
            a.history_state = "pending"
            a.history_indexed_at = None
            a.history_rows = None
            a.history_truncated = False
        kinds = ["history_index", "stats"]
    else:
        kinds = ["stats"]
    if not history:
        kinds = [k for k in kinds if k not in HISTORY_KINDS]
    db.commit()
    ops = enqueue_chain(
        db,
        kinds,
        repository_id=repository.id,
        trigger="manual",
        priority=PRIORITY_RECONCILE,
        triggered_by_user_id=current_user.id,
    )
    return {"run_id": ops[0].run_id if ops else None, "operations": [o.id for o in ops]}


# -- Pro routes (spec 11.2) -------------------------------------------------------

MAX_LIMIT = 500
ARCHIVE_HISTORY = require_feature("archive_history")


def _serialize_change(c: Change) -> dict:
    return {
        "path": c.path,
        "change": c.change,
        "size_before": c.size_before,
        "size_after": c.size_after,
        "mode_changed": c.mode_changed,
        "owner_changed": c.owner_changed,
        "summary_count": c.summary_count,
    }


def _totals(changes: list[Change]) -> dict:
    totals = {"added": 0, "removed": 0, "modified": 0, "summary": 0}
    for c in changes:
        totals[c.change] = totals.get(c.change, 0) + 1
    return totals


@router.get("/{repo_id}/archives/{archive_id}/changes", dependencies=[ARCHIVE_HISTORY])
async def archive_changes(
    repo_id: int,
    archive_id: int,
    compare_to: Optional[int] = None,
    path_prefix: Optional[str] = None,
    change: Optional[list[str]] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    cursor: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Changes of one archive against its predecessor, or against an older
    archive of the same series with the intermediate deltas folded (spec
    9.2). `cursor` is an offset into the filtered, path-ordered result."""
    repository = _repo(db, current_user, repo_id)
    target = _archive_or_404(db, repository, archive_id)
    predecessor = predecessor_of(db, target)
    base = {
        "archive_id": target.id,
        "history_state": target.history_state,
        "history_truncated": target.history_truncated,
    }
    if compare_to is None:
        compare = predecessor
    else:
        compare = _archive_or_404(db, repository, compare_to)
        if compare.series != target.series or compare.start >= target.start:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.archives.compareMustBeOlderInSeries"},
            )
    if target.history_state != "indexed":
        return {
            **base,
            "compare_to_id": compare.id if compare else None,
            "changes": [],
            "totals": _totals([]),
            "next_cursor": None,
        }
    if compare is None or (predecessor is not None and compare.id == predecessor.id):
        changes = list(
            rows_to_changes(
                db.query(ArchiveChange)
                .filter(ArchiveChange.archive_id == target.id)
                .all()
            ).values()
        )
    else:
        between = (
            db.query(Archive)
            .filter(
                Archive.repository_id == repository.id,
                Archive.series == target.series,
                Archive.start > compare.start,
                Archive.start <= target.start,
            )
            .order_by(Archive.start.asc(), Archive.id.asc())
            .all()
        )
        deltas = [
            rows_to_changes(
                db.query(ArchiveChange).filter(ArchiveChange.archive_id == a.id).all()
            )
            for a in between
        ]
        changes = list(fold_sequence(deltas).values())
    if path_prefix:
        changes = [c for c in changes if c.path.startswith(path_prefix)]
    if change:
        wanted = set(change)
        changes = [c for c in changes if c.change in wanted]
    changes.sort(key=lambda c: c.path)
    page = changes[cursor : cursor + limit]
    next_cursor = cursor + limit if cursor + limit < len(changes) else None
    return {
        **base,
        "compare_to_id": compare.id if compare else None,
        "changes": [_serialize_change(c) for c in page],
        "totals": _totals(changes),
        "next_cursor": next_cursor,
    }


def present_ranges(entries: list[dict]) -> list[dict]:
    """`entries` ascending by start with keys series, archive_id, change.
    A range opens at an added or modified entry and closes at a removed one;
    an open range ends with `to_archive_id` None (still present)."""
    ranges: list[dict] = []
    open_by_series: dict[str, dict] = {}
    for e in entries:
        current = open_by_series.get(e["series"])
        if e["change"] in ("added", "modified"):
            if current is None:
                current = {
                    "series": e["series"],
                    "from_archive_id": e["archive_id"],
                    "to_archive_id": None,
                }
                open_by_series[e["series"]] = current
                ranges.append(current)
        elif e["change"] == "removed" and current is not None:
            current["to_archive_id"] = e["archive_id"]
            del open_by_series[e["series"]]
    return ranges


@router.get("/{repo_id}/history", dependencies=[ARCHIVE_HISTORY])
async def path_history(
    repo_id: int,
    path: str = Query(min_length=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    rows = (
        db.query(ArchiveChange, Archive)
        .join(Archive, Archive.id == ArchiveChange.archive_id)
        .filter(Archive.repository_id == repository.id, ArchiveChange.path == path)
        .order_by(Archive.start.asc(), Archive.id.asc())
        .all()
    )
    ascending = [
        {
            "archive_id": a.id,
            "archive_name": a.name,
            "series": a.series,
            "start": a.start,
            "change": c.change,
            "size_before": c.size_before,
            "size_after": c.size_after,
            "mode_changed": c.mode_changed,
            "owner_changed": c.owner_changed,
        }
        for c, a in rows
    ]
    ranges = present_ranges(ascending)
    newest = (
        db.query(Archive)
        .filter(Archive.repository_id == repository.id)
        .order_by(Archive.start.desc(), Archive.id.desc())
        .first()
    )
    present_in_latest = bool(
        newest
        and any(
            r["series"] == newest.series and r["to_archive_id"] is None for r in ranges
        )
    )
    return {
        "path": path,
        "entries": list(reversed(ascending)),
        "present": ranges,
        "present_in_latest": present_in_latest,
    }


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/{repo_id}/search", dependencies=[ARCHIVE_HISTORY])
async def search_paths(
    repo_id: int,
    q: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Filename search over archive_changes.path, grouped by path (spec
    9.2). Case-insensitive LIKE; FTS5 is a listed follow-up."""
    repository = _repo(db, current_user, repo_id)
    pattern = f"%{_like_escape(q)}%"
    rows = (
        db.query(
            ArchiveChange.path,
            ArchiveChange.change,
            Archive.id,
            Archive.start,
            Archive.series,
        )
        .join(Archive, Archive.id == ArchiveChange.archive_id)
        .filter(
            Archive.repository_id == repository.id,
            ArchiveChange.change != "summary",
            func.lower(ArchiveChange.path).like(pattern.lower(), escape="\\"),
        )
        .order_by(ArchiveChange.path.asc(), Archive.start.asc(), Archive.id.asc())
        .all()
    )
    grouped: dict[str, dict] = {}
    for path, change, archive_id, start, series in rows:
        entry = grouped.setdefault(
            path,
            {
                "path": path,
                "first_seen_archive_id": archive_id,
                "first_seen": start,
                "last_seen_archive_id": archive_id,
                "last_seen": start,
                "archive_count": 0,
                "series": series,
                "last_change": change,
            },
        )
        entry["archive_count"] += 1
        entry["last_seen_archive_id"] = archive_id
        entry["last_seen"] = start
        entry["last_change"] = change
    results = list(grouped.values())
    for entry in results:
        entry["present_in_latest"] = entry.pop("last_change") != "removed"
    truncated = len(results) > limit
    return {"query": q, "results": results[:limit], "truncated": truncated}
