"""Database-backed archive routes (spec section 9.2): list, detail,
heatmap, status, rebuild, and (Pro) changes, history, search."""

import asyncio
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import UUID4, BaseModel, Field
from sqlalchemy import and_, case, func
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
    RepositorySizeSample,
)
from app.services.operations import anomalies
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.executors.history import (
    MAX_HISTORY_ATTEMPTS,
    SIZE_LOOKUP_CHUNK,
    predecessor_of,
    successor_of,
)
from app.services.operations.followups import (
    HISTORY_AGENT_UNSUPPORTED,
    HISTORY_AVAILABLE,
    PLAN_GATED_KINDS,
    history_capability,
    history_enabled,
)
from app.services.operations.history_fold import Change, fold_sequence, rows_to_changes
from app.services.operations.index_mode import filter_kinds
from app.services.operations.index_mode import mode_of as index_mode_of
from app.services.operations.reconcile import enqueue_reconcile_run
from app.services.operations.repository_status import repository_status
from app.services.operations.series import (
    crons_for_repository,
    retention_days_for_repository,
)
from app.services.operations.runner import operation_runner
from app.services.operations.vocab import PRIORITY_RECONCILE, SUCCESS_STATUSES

router = APIRouter()

NOT_FOUND = {"key": "backend.errors.archives.notFound"}
# Three intervals, so one missed reconcile (a backend restart sleeps a
# full interval before its first run) does not flip every chip to stale.
STALE_AFTER_INTERVALS = 3


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
        "stats_measured_at": a.stats_measured_at,
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
    settings = db.query(SystemSettings).first()
    interval = (settings.stats_refresh_interval_minutes if settings else None) or 60
    return sync_state_from(active is not None, last_at, interval), last_at


def sync_state_from(
    active: bool, last_at: Optional[datetime], interval_minutes: int
) -> str:
    """The archive index freshness rule on its own, so callers that already
    hold the per-repository facts (the Background work hub reads them for
    every repository in two queries) do not repeat the lookups."""
    if active:
        return "syncing"
    if last_at is None:
        return "never"
    # DB timestamps round-trip as naive UTC (spec 6.1); compare against a
    # naive "now" rather than utc_now()'s tz-aware value.
    if utc_now().replace(tzinfo=None) - last_at > timedelta(
        minutes=interval_minutes * STALE_AFTER_INTERVALS
    ):
        return "stale"
    return "fresh"


def _naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Archive.start and Operation timestamps round-trip as naive UTC, so a
    query param that carries an offset (`?until=...Z`) is converted before it
    is compared with them or handed to the anomaly helpers."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def completed_backup_days(
    db: Session, repository: Repository, since: Optional[datetime], until: datetime
) -> set[date]:
    """Days with a completed backup operation on this repository.

    Run evidence for the missed-run rule: the archive of such a run may have
    been pruned since (#966 keeps the row and marks `archive_pruned_at`), and
    a day that provably ran is not a missed day (issue #943).
    """
    ran_at = func.coalesce(Operation.started_at, Operation.created_at)
    q = db.query(ran_at).filter(
        Operation.repository_id == repository.id,
        Operation.kind == "backup",
        Operation.status.in_(tuple(SUCCESS_STATUSES)),
        ran_at <= until,
    )
    if since is not None:
        q = q.filter(ran_at >= since)
    return {value.date() for (value,) in q.all() if value is not None}


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
    # The plan lookup commits the session; read it before the rows so the
    # commit cannot expire them (one refresh per archive otherwise; the
    # repository row alone is refreshed once).
    history = history_enabled(db)
    rows = (
        _archives_query(db, repository, series, _naive_utc(since), _naive_utc(until))
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
        # `history_available` keeps its meaning (the plan has the feature);
        # the capability says whether this repository has the stage, and
        # why not.
        "history_available": history,
        "history_capability": history_capability(db, repository, history=True),
    }


@router.get("/{repo_id}/archives/heatmap")
async def archives_heatmap(
    repo_id: int,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The archive index drawn as a calendar.

    One band for the repository holding every archive the index has, the same
    set and the same window the list shows, plus the same archives grouped by
    series for readers who want the split. Series inference is a naming
    heuristic (spec 6.6) and must never decide whether an archive is visible
    (issue #943), so the window has no default either: what the list shows,
    the heatmap shows.
    """
    repository = _repo(db, current_user, repo_id)
    until = _naive_utc(until) or utc_now().replace(tzinfo=None)
    since = _naive_utc(since)
    rows = (
        _archives_query(db, repository, None, since, until)
        .order_by(Archive.start.asc(), Archive.id.asc())
        .all()
    )
    crons = crons_for_repository(db, repository)
    by_series: dict[str, list[Archive]] = {}
    for a in rows:
        by_series.setdefault(a.series, []).append(a)
    # Outliers stay scoped to the series even though the days are not: a
    # repository holding a 3 GB documents series and a 200 GB media series
    # would otherwise compare each archive with whatever ran before it.
    # On every plan: the flags compare original_size, nfiles and duration
    # between neighbouring archives, all of which the archive list already
    # shows the reader. An archive that came out unusually small usually
    # means a source was missing when it ran, which is a warning about
    # their data rather than a convenience (spec 2026-09-21, section 1.3).
    flags: dict[int, list[str]] = {}
    for archives in by_series.values():
        flags.update(anomalies.series_flags(archives))

    def band(name: Optional[str], archives: list[Archive]) -> dict:
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
        out = {
            "days": list(days.values()),
            "first": archives[0].start if archives else None,
            "last": archives[-1].start if archives else None,
            "count": len(archives),
        }
        if name is not None:
            out["series"] = name
        return out

    retention_days = retention_days_for_repository(db, repository)
    retention_since = (
        (until - timedelta(days=retention_days)).date()
        if retention_days is not None
        else None
    )
    missed = anomalies.missed_run_days(
        [a.start for a in rows],
        until=until,
        crons=crons,
        run_days=completed_backup_days(db, repository, since, until),
        retention_since=retention_since,
    )
    repository_band = band(None, rows)
    repository_band["missed_days"] = sorted(d.isoformat() for d in missed)
    return {
        "since": since,
        "until": until,
        "repository": repository_band,
        "series": [band(name, archives) for name, archives in by_series.items()],
        "cadence_known": bool(crons),
        "retention_since": retention_since.isoformat() if retention_since else None,
    }


def _attach_repository_sizes(
    db: Session, repository_id: int, points: list[dict], boundaries: list
) -> None:
    """The repository's measured size after each archive: the last sample
    taken between that archive's start and the next archive's (or now, for
    the newest). The boundaries come from every surviving archive, not just
    the plotted ones, so a sample taken after an archive that is unmeasured
    or filtered out is not credited to the point before it. Archives older
    than the first sample keep None; the history starts when the sampling
    did."""
    if not points:
        return
    samples = (
        db.query(RepositorySizeSample.measured_at, RepositorySizeSample.size_bytes)
        .filter(RepositorySizeSample.repository_id == repository_id)
        .order_by(RepositorySizeSample.measured_at.asc(), RepositorySizeSample.id.asc())
        .all()
    )
    if not samples:
        return
    # Both lists run oldest first, so one cursor walks the samples once.
    cursor = 0
    window: Optional[tuple] = None
    last = None
    for point in points:
        lower = point["start"]
        after = bisect_right(boundaries, lower)
        upper = boundaries[after] if after < len(boundaries) else None
        if window != (lower, upper):
            # a new window; two archives started at the same instant share
            # theirs and keep the value already read for it
            window = (lower, upper)
            while cursor < len(samples) and samples[cursor][0] < lower:
                cursor += 1
            last = None
            while cursor < len(samples) and (
                upper is None or samples[cursor][0] < upper
            ):
                last = samples[cursor][1]
                cursor += 1
        if last is not None:
            point["repository_size"] = last


@router.get("/{repo_id}/archives/growth")
async def archives_growth(
    repo_id: int,
    series: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The archive index as a growth curve (spec 4.3).

    One point per measured archive, oldest first: what the archive added to
    the repository (deduplicated_size) and the running total of those
    additions, which is at least the repository footprint after that backup
    (chunks shared only among archives are in nobody's number). Filtered
    to a series the total restarts, so the curve is that series' footprint.
    Archives the info fill has not measured have no point. A stale point
    (measured once, then a listing saw archives removed) keeps its value
    and is flagged, per spec 4.1.

    Declared before the `{archive_id}` route on purpose: that route's path
    parameter matches any segment, so `growth` would otherwise reach it and
    fail validation.
    """
    repository = _repo(db, current_user, repo_id)
    rows = (
        _archives_query(db, repository, series, None, None)
        .order_by(Archive.start.asc(), Archive.id.asc())
        .all()
    )
    # Every surviving archive bounds a size sample's window, even the ones
    # this curve does not plot (unmeasured, or another series).
    boundary_q = db.query(Archive.start).filter(Archive.repository_id == repository.id)
    boundaries = [s for (s,) in boundary_q.order_by(Archive.start.asc()).all()]
    series_q = db.query(Archive.series).filter(Archive.repository_id == repository.id)
    all_series = [
        s for (s,) in series_q.distinct().order_by(Archive.series.asc()).all()
    ]
    points: list[dict] = []
    running = 0
    unmeasured = 0
    for a in rows:
        if a.deduplicated_size is None:
            unmeasured += 1
            continue
        running += a.deduplicated_size
        points.append(
            {
                "archive_id": a.id,
                "name": a.name,
                "series": a.series,
                "start": a.start,
                "deduplicated_size": a.deduplicated_size,
                "original_size": a.original_size,
                "running_total": running,
                "repository_size": None,
                "stale": a.stats_measured_at is None,
            }
        )
    _attach_repository_sizes(db, repository.id, points, boundaries)
    return {
        "points": points,
        "series": all_series,
        "stale_count": sum(1 for p in points if p["stale"]),
        "unmeasured_count": unmeasured,
    }


class PrunePreviewRequest(BaseModel):
    keep_hourly: int = Field(default=0, ge=0)
    keep_daily: int = Field(default=0, ge=0)
    keep_weekly: int = Field(default=0, ge=0)
    keep_monthly: int = Field(default=0, ge=0)
    keep_quarterly: int = Field(default=0, ge=0)
    keep_yearly: int = Field(default=0, ge=0)
    keep_within: Optional[str] = None
    # One run per visit to the preview page, so the dry runs a reader sets
    # off while trying policies land as steps of one run in the timeline
    # instead of as loose rows. A UUID, so a client cannot join its rows to
    # a run the server owns.
    preview_run_id: Optional[UUID4] = None


@router.post("/{repo_id}/prune/preview")
async def prune_preview(
    repo_id: int,
    body: PrunePreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spec 4.4: Borg's dry run joined to the index, candidates re-measured,
    freed space as a lower bound, and (Pro) the files no surviving archive
    of the series would hold. Declared before the `{archive_id}` routes on
    purpose, as `archives_growth` is."""
    from app.api.repositories import _normalize_prune_keep_within
    from app.services import prune_preview as service

    repository = _repo(db, current_user, repo_id, role="operator")
    retention = service.Retention(
        keep_hourly=body.keep_hourly,
        keep_daily=body.keep_daily,
        keep_weekly=body.keep_weekly,
        keep_monthly=body.keep_monthly,
        keep_quarterly=body.keep_quarterly,
        keep_yearly=body.keep_yearly,
        keep_within=_normalize_prune_keep_within(body.keep_within),
    )
    if not retention.has_rule:
        raise HTTPException(
            status_code=400, detail={"key": "backend.errors.prune.noKeepRule"}
        )
    try:
        return await service.build_preview(
            db,
            repository,
            retention,
            user_id=current_user.id,
            run_id=str(body.preview_run_id) if body.preview_run_id else None,
        )
    except service.DryRunFailed as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "key": "backend.errors.prune.dryRunFailed",
                "params": {"log": exc.log},
            },
        )


@router.get("/{repo_id}/prune/comparison")
async def prune_comparison(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spec 4.5: the stored retention comparison, with `stale` when the
    archive count moved since it was computed."""
    from app.services.prune_compare import stored

    return stored(db, _repo(db, current_user, repo_id))


@router.get("/{repo_id}/prune/comparison/{candidate}/preview")
async def prune_comparison_preview(
    repo_id: int,
    candidate: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """A stored candidate as the full preview payload. The comparison already
    ran Borg for this policy and kept its verdicts, so opening the row is a
    read: no dry run, no entry in the timeline."""
    from app.database.models import PruneComparison
    from app.services import prune_preview as service

    repository = _repo(db, current_user, repo_id)
    row = (
        db.query(PruneComparison)
        .filter(
            PruneComparison.repository_id == repository.id,
            PruneComparison.candidate == candidate,
        )
        .first()
    )
    if row is None or row.verdicts is None:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.prune.candidateNotStored"}
        )
    return service.preview_from_verdicts(
        db,
        repository,
        [service.Verdict(*v) for v in row.verdicts],
        operation_id=row.operation_id,
    )


@router.post("/{repo_id}/prune/comparison/refresh")
async def prune_comparison_refresh(
    repo_id: int,
    auto: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """`auto` is the preview page opening on a comparison that is missing or
    stale, as against the reader pressing Compare now: the same work, but the
    timeline should not call it manual."""
    from app.services.operations.enqueue import enqueue

    repository = _repo(db, current_user, repo_id, role="operator")
    pending = (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "prune_compare",
            Operation.status.in_(("queued", "running")),
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.prune.comparisonRunning"}
        )
    op = enqueue(
        db,
        "prune_compare",
        repository_id=repository.id,
        trigger="preview" if auto else "manual",
        triggered_by_user_id=current_user.id,
    )
    return {"operation_id": op.id}


@router.get("/{repo_id}/prune/retention-defaults")
async def prune_retention_defaults(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.prune_preview import retention_defaults

    return retention_defaults(db, _repo(db, current_user, repo_id))


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
    history = history_enabled(db)  # commits; before the archive rows load
    archive = _archive_or_404(db, repository, archive_id)
    predecessor = predecessor_of(db, archive)
    successor = successor_of(db, archive)
    return {
        **serialize_archive(archive),
        "predecessor_id": predecessor.id if predecessor else None,
        "successor_id": successor.id if successor else None,
        # The header's deltas (spec 4.2) come from here rather than a second
        # request for the predecessor.
        "predecessor_stats": (
            {
                "id": predecessor.id,
                "nfiles": predecessor.nfiles,
                "original_size": predecessor.original_size,
                "deduplicated_size": predecessor.deduplicated_size,
                "duration_seconds": predecessor.duration_seconds,
            }
            if predecessor
            else None
        ),
        "history_available": history,
        "history_capability": history_capability(db, repository, history=True),
    }


@router.get("/{repo_id}/status")
async def repository_status_route(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-category status from the best evidence available (#935): the
    archive list for backups, detected removals for prune, job rows for
    check and compact, with expectations from the series cadence and the
    repository's own plans and schedules."""
    repository = _repo(db, current_user, repo_id)
    return repository_status(
        db,
        repository,
        now=utc_now().replace(tzinfo=None),
        pro=history_enabled(db),
    )


# Kinds that write `archive_changes` rows. A run in flight took its archive
# list, its excludes and its row cap before the rebuild, and goes on writing
# rows (and marking archives `indexed`) after the rebuild deleted them, so a
# `from = history` rebuild has to stop it first (#1079). archive_sync's fold
# of a removed archive also writes rows, but reads the states it folds in the
# same synchronous step, so a rebuild before it leaves nothing stale to write.
HISTORY_WRITE_KINDS = ("history_index",)
# Cancellation is cooperative: the executor sees the flag between two lines
# of `borg diff`, and a diff of two large archives can be silent for a long
# time (the reason `history_index` is not cancellable from the UI either).
# So the wait is short, and a run that does not stop in it refuses the
# rebuild rather than having its rows deleted and written back.
CANCEL_WAIT_SECONDS = 10.0


async def _stop_history_writers(db: Session, repository_id: int) -> None:
    """Leave no history writer running on the repository, or refuse.

    Waiting for one is itself an await, and the run ending there wakes the
    runner, which can claim the next queued writer of the repository before
    this coroutine resumes. So the list is read again after every wait, and
    what has started since is stopped in its turn, until nothing is running
    or the budget is spent."""
    deadline = monotonic() + CANCEL_WAIT_SECONDS
    while True:
        # The executor commits from its own session; end this one's read
        # transaction so the states come from disk rather than a snapshot
        # taken before the cancel.
        db.rollback()
        op = (
            db.query(Operation)
            .filter(
                Operation.repository_id == repository_id,
                Operation.kind.in_(HISTORY_WRITE_KINDS),
                Operation.status == "running",
            )
            .order_by(Operation.id.asc())
            .first()
        )
        if op is None:
            return
        # Read before the cancel: the runner drops the task as it finishes,
        # and a run that ended on its own meanwhile needs no waiting.
        task = operation_runner.running_tasks.get(op.id)
        await operation_runner.request_cancel(op.id)
        remaining = deadline - monotonic()
        if task is not None and remaining > 0:
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if done:
                continue
        elif task is None:
            # No task here: the row is another worker's, or it ended between
            # the query and the cancel. Only the second one lets this go on.
            db.rollback()
            if db.get(Operation, op.id).status != "running":
                continue
        raise HTTPException(
            status_code=409,
            detail={
                "key": "backend.errors.archives.historyRunning",
                "params": {"operationId": op.id},
            },
        )


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
    # The chain that gets rebuilt is the chain that runs in the background,
    # and that one is plan independent: only the executor can refuse the
    # history stage. Wiping and rebuilding the change rows by hand stays Pro
    # (the `history` branch below), since it is an expensive tool for a
    # feature the reader cannot see.
    capability = history_capability(db, repository, history=True)
    if body.from_stage == "history" and capability == HISTORY_AGENT_UNSUPPORTED:
        # A rebuild that can only skip again would reset every archive to
        # `pending` for nothing and read as "not yet" in the UI. Before the
        # plan gate: an upgrade would not make this rebuild work.
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.archives.historyUnavailableForAgent"},
        )
    if body.from_stage == "history":
        require_feature_access(db, "archive_history")
        # Nothing between here and the commit below awaits, so the runner
        # cannot claim a queued writer of this repository while the rows are
        # being deleted: it runs in this process (both entrypoints pin
        # gunicorn to `--workers 1`, and the repository command lock is an
        # in-process asyncio lock for the same reason), so it only advances
        # at an await of this coroutine. A writer that starts after the
        # commit reads the archive list, the excludes and the row cap fresh,
        # which is the point of the rebuild.
        await _stop_history_writers(db, repository.id)
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
            a.history_attempts = 0
            a.history_indexed_at = None
            a.history_rows = None
            a.history_truncated = False
        kinds = ["history_index", "stats"]
    else:
        kinds = ["stats"]
    if capability != HISTORY_AVAILABLE:
        kinds = [k for k in kinds if k not in PLAN_GATED_KINDS]
    mode = index_mode_of(repository)
    # Spec 6.8: manual work is not blocked by the mode, but a mode that
    # excludes file history is a standing instruction not to diff this
    # repository, so the history stages go and the listing and the size
    # still run this once.
    kinds = filter_kinds("archives" if mode == "off" else mode, kinds)
    db.commit()
    ops = enqueue_chain(
        db,
        kinds,
        repository_id=repository.id,
        trigger="manual",
        priority=PRIORITY_RECONCILE,
        triggered_by_user_id=current_user.id,
    )
    return {
        "run_id": ops[0].run_id if ops else None,
        "operations": [o.id for o in ops],
    }


@router.post("/{repo_id}/resync")
async def resync(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bring the stored archive list back in line with the repository after
    work that removed archives (delete, prune, wipe). Unlike /rebuild this
    invalidates nothing: archive_sync reconciles the list and folds the rows
    of archives that have gone, and stats refreshes the totals. A run already in flight is reused rather than duplicated.

    An `off` repository is listed once here and then goes quiet again, and a
    mode that excludes file history keeps excluding it (spec 6.8)."""
    repository = _repo(db, current_user, repo_id, role="operator")
    ops = enqueue_reconcile_run(db, repository.id, manual=True)
    return {
        "run_id": ops[0].run_id if ops else None,
        "operations": [o.id for o in ops],
    }


# -- Pro routes (spec 11.2) -------------------------------------------------------

MAX_LIMIT = 500
ARCHIVE_HISTORY = require_feature("archive_history")

# What a Community reader gets from the three history routes: the counts,
# and for search a handful of real rows. The file level answer is Pro (spec
# 2026-09-21-community-teasers-and-feature-trials, section 1). The routes
# carry no feature dependency for that reason; each one shapes its own
# response and says so with `detail_locked`.
TEASER_SEARCH_ROWS = 3
# Counting every distinct match would scan the whole change table for a
# broad query. The teaser says "500+" past this and stops counting.
TEASER_SEARCH_COUNT_CAP = 500


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


@router.get("/{repo_id}/archives/{archive_id}/changes")
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
    history = history_enabled(db)  # commits; before the archive rows load
    target = _archive_or_404(db, repository, archive_id)
    predecessor = predecessor_of(db, target)
    base = {
        "archive_id": target.id,
        "history_state": target.history_state,
        "history_truncated": target.history_truncated,
        "history_capability": history_capability(db, repository, history=True),
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
            "detail_locked": not history,
            "totals": _totals([]),
            "next_cursor": None,
            "incomplete": True,
            "unindexed_archive_ids": [target.id],
        }
    unindexed: list[int] = []
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
        # An archive that was never indexed has no rows, so it would fold in as
        # an empty delta and quietly drop whatever changed in its window.
        unindexed = [a.id for a in between if a.history_state != "indexed"]
        # One query for the whole window: a row per archive turned this into N
        # round trips over a table capped per archive, not in total.
        by_archive: dict[int, list] = {a.id: [] for a in between}
        # Chunked like known_sizes in the history executor: one bind parameter
        # per archive, and older SQLite builds cap those at 999, which a few
        # years of daily backups passes.
        ids = list(by_archive)
        for i in range(0, len(ids), SIZE_LOOKUP_CHUNK):
            for row in db.query(ArchiveChange).filter(
                ArchiveChange.archive_id.in_(ids[i : i + SIZE_LOOKUP_CHUNK])
            ):
                by_archive[row.archive_id].append(row)
        deltas = [rows_to_changes(by_archive[a.id]) for a in between]
        changes = list(fold_sequence(deltas).values())
    if path_prefix:
        changes = [c for c in changes if c.path.startswith(path_prefix)]
    # The totals feed the filter chips, so they count the whole comparison
    # (within the path scope) rather than the change types currently shown.
    totals = _totals(changes)
    if change:
        wanted = set(change)
        changes = [c for c in changes if c.change in wanted]
    changes.sort(key=lambda c: c.path)
    page = changes[cursor : cursor + limit]
    next_cursor = cursor + limit if cursor + limit < len(changes) else None
    return {
        **base,
        "compare_to_id": compare.id if compare else None,
        # The totals are the Community teaser; the rows behind them are Pro.
        "changes": [_serialize_change(c) for c in page] if history else [],
        "detail_locked": not history,
        "totals": totals,
        "next_cursor": next_cursor if history else None,
        "incomplete": bool(unindexed),
        "unindexed_archive_ids": unindexed,
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


@router.get("/{repo_id}/history")
async def path_history(
    repo_id: int,
    path: str = Query(min_length=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    history = history_enabled(db)  # commits; before the archive rows load
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
    # What the answer is based on: with nothing indexed the entries say
    # nothing about the path, and with a partial index they cover only the
    # indexed archives. `total` counts every archive, `skipped` ones
    # included: they are not covered either, whether an agent's repository
    # will never index them (the capability says so) or a server's still
    # carries them from an agent-executed past. `exhausted` are the failures
    # the executor gave up on.
    total, indexed, exhausted = (
        db.query(
            func.count(Archive.id),
            func.sum(case((Archive.history_state == "indexed", 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            Archive.history_state == "failed",
                            Archive.history_attempts >= MAX_HISTORY_ATTEMPTS,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        .filter(Archive.repository_id == repository.id)
        .one()
    )
    return {
        "path": path,
        # How many versions of this path the index holds, and the window they
        # cover: the Community teaser for one file. The versions themselves
        # are Pro.
        "versions": len(ascending),
        "first_seen": ascending[0]["start"] if ascending else None,
        "last_seen": ascending[-1]["start"] if ascending else None,
        "detail_locked": not history,
        "entries": list(reversed(ascending)) if history else [],
        "present": ranges if history else [],
        "present_in_latest": present_in_latest,
        "coverage": {
            "indexed": int(indexed or 0),
            "exhausted": int(exhausted or 0),
            "total": int(total or 0),
            "capability": history_capability(db, repository, history=True),
        },
    }


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_filter(repository: Repository, q: str):
    pattern = f"%{_like_escape(q)}%".lower()
    return (
        Archive.repository_id == repository.id,
        ArchiveChange.change != "summary",
        func.lower(ArchiveChange.path).like(pattern, escape="\\"),
    )


def matching_paths(
    db: Session, repository: Repository, q: str, limit: int
) -> tuple[list[str], bool]:
    """The page of distinct paths a search returns, bounded in SQL. Grouping
    every matching change row first meant a broad query loaded the whole table
    before the limit was applied."""
    rows = (
        db.query(ArchiveChange.path)
        .join(Archive, Archive.id == ArchiveChange.archive_id)
        .filter(*_search_filter(repository, q))
        .distinct()
        .order_by(ArchiveChange.path.asc())
        .limit(limit + 1)
        .all()
    )
    paths = [p for (p,) in rows]
    return paths[:limit], len(paths) > limit


def search_match_count(
    db: Session, repository: Repository, q: str, cap: int = TEASER_SEARCH_COUNT_CAP
) -> tuple[int, bool]:
    """Distinct paths a search matches, stopped at `cap`. The second value
    says the count is a floor, which the UI renders as "500+"."""
    inner = (
        db.query(ArchiveChange.path)
        .join(Archive, Archive.id == ArchiveChange.archive_id)
        .filter(*_search_filter(repository, q))
        .distinct()
        .limit(cap + 1)
        .subquery()
    )
    found = db.query(func.count()).select_from(inner).scalar() or 0
    return (cap, True) if found > cap else (found, False)


def rows_for_paths(db: Session, repository: Repository, paths: list[str]) -> list:
    """The change rows of the paths on this page, oldest archive first."""
    if not paths:
        return []
    return (
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
            ArchiveChange.path.in_(paths),
        )
        .order_by(ArchiveChange.path.asc(), Archive.start.asc(), Archive.id.asc())
        .all()
    )


@router.get("/{repo_id}/search")
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
    pro = history_enabled(db)  # commits; before the archive rows load
    if not pro:
        limit = TEASER_SEARCH_ROWS
    paths, truncated = matching_paths(db, repository, q, limit)
    rows = rows_for_paths(db, repository, paths)
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
    if not pro:
        # The count is what makes the case; the rows past the first few are
        # the feature.
        match_count, capped = search_match_count(db, repository, q)
        return {
            "query": q,
            "results": results,
            "truncated": truncated,
            "detail_locked": True,
            "match_count": match_count,
            "match_count_capped": capped,
        }
    return {
        "query": q,
        "results": results,
        "truncated": truncated,
        "detail_locked": False,
    }
