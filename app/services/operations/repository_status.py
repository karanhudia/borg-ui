"""Repository status from repository evidence (#935, spec 10.2).

Each cell uses the best evidence available. Backup and prune have evidence
in the repository itself (the archive list, archives that disappeared
between two listings); check and compact only have Borg UI's own job
rows, since Borg records neither. Job rows stay secondary evidence for the
first two: a failed attempt newer than the newest archive is real
information about the last run, and a repository with no archives at all
falls back to whatever job ran last.

The `source` of a cell is kept for precedence and debugging; the UI does
not label it.

`last_runs` serves the repository card's metadata row (`Last prune`,
`Last index`) for a whole page of repositories at once, from the same
evidence rules; the row counts successful runs only, the route also
reports a newer failed attempt as such.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Iterable, Optional

from sqlalchemy import String, and_, case, cast, func, or_
from sqlalchemy.orm import Session, aliased

from app.database.models import (
    Archive,
    BackupPlan,
    BackupPlanRepository,
    Operation,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
)
from app.services.operations import anomalies
from app.services.operations.index_mode import mode_of as index_mode_of
from app.services.operations.vocab import SUCCESS_STATUSES
from app.services.storage_usage import (
    SOURCE_ARCHIVE_SUMS,
    SOURCE_BORG1_CACHE_STATS,
    SOURCE_COMPACT_STATS,
    stored_size_bytes,
)

TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")
FAILED = ("failed", "cancelled")
CELLS: tuple[tuple[str, dict], ...] = (
    ("backup", {"kinds": ("backup",)}),
    ("check", {"kinds": ("check",)}),
    ("prune", {"kinds": ("prune",)}),
    ("compact", {"kinds": ("compact",)}),
    ("index", {"category": "index"}),
    ("mirror", {"category": "mirror"}),
)
CADENCE_FACTOR = 2


@dataclass
class CellStatus:
    cell: str
    status: Optional[str] = None
    completed_at: Optional[datetime] = None
    running: bool = False
    source: Optional[str] = None
    threshold_days: Optional[int] = None
    overdue: Optional[bool] = None

    def as_dict(self, now: datetime) -> dict:
        return {
            "cell": self.cell,
            "status": self.status,
            "completed_at": self.completed_at,
            "age_seconds": (now - self.completed_at).total_seconds()
            if self.completed_at
            else None,
            "threshold_days": self.threshold_days,
            "overdue": self.overdue,
            "running": self.running,
            "source": self.source,
        }


# -- evidence ---------------------------------------------------------------------


def _not_dry_run():
    """A prune preview is a completed `prune` operation with
    `params.dry_run` set; it removed nothing and is not prune evidence."""
    flag = Operation.params["dry_run"].as_boolean()
    return func.coalesce(flag, False).is_(False)


def _operations(db: Session, repository_id: int, spec: dict):
    q = db.query(Operation).filter(Operation.repository_id == repository_id)
    if "kinds" in spec:
        return q.filter(Operation.kind.in_(spec["kinds"]))
    return q.filter(Operation.category == spec["category"])


def job_evidence(db: Session, repository_id: int, cell: str, spec: dict) -> CellStatus:
    """The newest terminal operation for a cell, plus whether one is
    running."""
    q = _operations(db, repository_id, spec)
    running = q.filter(Operation.status == "running").first() is not None
    # a running prune preview still shows as running; a finished one is no
    # evidence of a prune
    if "prune" in spec.get("kinds", ()):
        q = q.filter(_not_dry_run())
    # completed_at is required: PostgreSQL sorts NULL first on DESC, so a
    # terminal row without a timestamp would hide newer evidence.
    latest = (
        q.filter(Operation.status.in_(TERMINAL), Operation.completed_at.isnot(None))
        .order_by(Operation.completed_at.desc())
        .first()
    )
    result = CellStatus(cell=cell, running=running)
    if latest:
        result.status, result.completed_at, result.source = (
            latest.status,
            latest.completed_at,
            "operations",
        )
    return result


def series_starts(db: Session, repository_id: int) -> dict[str, list[datetime]]:
    """Archive start times per series, each ascending. Archives without a
    series form one group of their own: a cadence is a property of a
    series, and timestamps of different series interleave (two nightly
    hosts a minute apart look hourly when mixed).

    Bounded to the newest CADENCE_SAMPLE archives per series: the cadence
    reads no further back and the newest archive is among them, so a long
    hourly history is not scanned on every status request."""
    rank = (
        func.row_number()
        .over(
            partition_by=Archive.series,
            order_by=(Archive.start.desc(), Archive.id.desc()),
        )
        .label("rank")
    )
    ranked = (
        db.query(Archive.series.label("series"), Archive.start.label("start"), rank)
        .filter(Archive.repository_id == repository_id)
        .subquery()
    )
    result: dict[str, list[datetime]] = {}
    for series, start in (
        db.query(ranked.c.series, ranked.c.start)
        .filter(ranked.c.rank <= anomalies.CADENCE_SAMPLE)
        .order_by(ranked.c.start.asc())
        .all()
    ):
        result.setdefault(series or "", []).append(start)
    return result


def _removal_criterion(db: Session, model=Operation):
    """SQL for "this archive_sync result lists removed archives", so the
    listings that matter are one query instead of a row-by-row JSON decode
    in Python. SQLite (JSON1, built into every Python since 3.9's bundled
    library) and PostgreSQL spell the array length differently; both
    return NULL for a missing key, which compares false. `model` is an
    alias of Operation when used inside a correlated subquery."""
    if db.get_bind().dialect.name == "postgresql":
        # json_array_length raises on a non-array; CASE evaluates in order
        removed = model.result.op("->")("removed_archive_ids")
        length = case(
            (func.json_typeof(removed) == "array", func.json_array_length(removed)),
            else_=0,
        )
    else:
        length = func.json_array_length(model.result, "$.removed_archive_ids")
    return and_(_listing_criterion(model), length > 0)


def _listing_criterion(model):
    return and_(
        model.kind == "archive_sync",
        model.status.in_(SUCCESS_STATUSES),
        model.completed_at.isnot(None),
    )


# Borg UI's own archive removals besides prune: `delete_archive` and `wipe`
# run as operations. A wipe preview is a `repository_wipe_jobs` row and
# removes nothing, so it is no evidence here.
# Any of these that started may have removed archives whatever its final
# status: a deletion cancelled or failed after Borg dropped the manifest
# entry still removed the archive, a wipe that failed half-way is recorded
# `failed`. One that never started (a cancelled preview, a queued
# operation cancelled before its turn) only carries a completed_at stamp.
DELETION_KINDS = ("delete_archive", "wipe")
# Removal listings read per repository and page, newest first. Each deletion
# explains at most one listing; when a whole page is explained the next
# page is read, so a long cleanup does not turn a cron prune into "never".
# A repository that is only ever cleaned up by hand would have every page
# explained, so the pages are capped and the value is unknown beyond them.
REMOVAL_CANDIDATES = 32
REMOVAL_PAGES = 4


def removal_listings_by_repository(
    db: Session, repository_ids: list[int], page: int = 0
) -> dict[int, list[datetime]]:
    """One page of REMOVAL_CANDIDATES successful listings that reported
    removed archives, newest first per repository. A sync the runner
    marked cancelled keeps its listing but gets no follow-ups, so its
    removals are not applied and the next successful listing reports them
    again."""
    rank = (
        func.row_number()
        .over(
            partition_by=Operation.repository_id,
            order_by=Operation.completed_at.desc(),
        )
        .label("rank")
    )
    ranked = (
        db.query(
            Operation.repository_id.label("repository_id"),
            Operation.completed_at.label("completed_at"),
            rank,
        )
        .filter(Operation.repository_id.in_(repository_ids), _removal_criterion(db))
        .subquery()
    )
    rows = (
        db.query(ranked.c.repository_id, ranked.c.completed_at)
        .filter(
            ranked.c.rank > page * REMOVAL_CANDIDATES,
            ranked.c.rank <= (page + 1) * REMOVAL_CANDIDATES,
        )
        .order_by(ranked.c.completed_at.desc())
        .all()
    )
    result: dict[int, list[datetime]] = {}
    for repository_id, completed_at in rows:
        result.setdefault(repository_id, []).append(completed_at)
    return result


def _removal_listing_before_by_repository(
    db: Session, before: dict[int, datetime]
) -> dict[int, datetime]:
    """The listing with removals before each repository's given one: a
    deletion explains the first listing with removals at or after it, so
    deletions up to this one explain listings outside the window."""
    rows = (
        db.query(Operation.repository_id, func.max(Operation.completed_at))
        .filter(
            _removal_criterion(db),
            or_(
                *[
                    and_(
                        Operation.repository_id == repository_id,
                        Operation.completed_at < at,
                    )
                    for repository_id, at in before.items()
                ]
            ),
        )
        .group_by(Operation.repository_id)
        .all()
    )
    return {repository_id: completed_at for repository_id, completed_at in rows}


def explained_listings_by_repository(
    db: Session, candidates: dict[int, list[datetime]]
) -> dict[int, set[datetime]]:
    """The listings whose removals Borg UI itself caused: for each deletion
    (a `delete_archive` or `wipe` operation that started), the first listing at or after it that reported removed
    archives is the one that reported them gone. Not merely the first
    listing: a sync already in flight when the deletion ran listed the
    archive as still present and reports nothing, and the one after it is
    the one that must not read as a prune. Bounded to the candidates
    (newest first per repository): a deletion after the newest one
    explains nothing in the window, one up to the removal listing that
    precedes the oldest explains a listing outside it. One query with a
    correlated minimum."""
    listing = aliased(Operation)
    result: dict[int, set[datetime]] = {}
    since = _removal_listing_before_by_repository(
        db, {repository_id: at[-1] for repository_id, at in candidates.items()}
    )

    def window(model):
        return or_(
            *[
                and_(
                    model.repository_id == repository_id,
                    model.completed_at <= at[0],
                    (model.completed_at > since[repository_id])
                    if repository_id in since
                    else True,
                )
                for repository_id, at in candidates.items()
            ]
        )

    done = and_(
        Operation.kind.in_(DELETION_KINDS),
        Operation.status.in_(TERMINAL),
        Operation.started_at.isnot(None),
    )
    first_listing = (
        db.query(func.min(listing.completed_at))
        .filter(
            listing.repository_id == Operation.repository_id,
            _removal_criterion(db, listing),
            listing.completed_at >= Operation.completed_at,
        )
        .correlate(Operation)
        .scalar_subquery()
    )
    rows = (
        db.query(Operation.repository_id, first_listing)
        .filter(done, Operation.completed_at.isnot(None), window(Operation))
        .all()
    )
    for repository_id, listed_at in rows:
        if listed_at is not None:
            result.setdefault(repository_id, set()).add(listed_at)
    return result


def prune_removal_evidence(
    db: Session, repository_ids: list[int]
) -> dict[int, Optional[datetime]]:
    """When archives were last seen to disappear without Borg UI having
    deleted them: the newest listing with removals that no deletion or
    wipe explains. An upper bound, since the removal happened between that
    listing and the one before. A listing a deletion explains is skipped,
    not the whole history, so one archive deleted from the Archives page
    does not turn a nightly cron prune into "never"; a prune outside Borg
    UI in a deletion's own interval is the one case that is missed. Reads
    REMOVAL_CANDIDATES listings per repository at a time and turns the
    page only for repositories whose whole page was explained, up to
    REMOVAL_PAGES pages."""
    result: dict[int, Optional[datetime]] = {}
    pending = list(repository_ids)
    page = 0
    while pending and page < REMOVAL_PAGES:
        listings = removal_listings_by_repository(db, pending, page)
        if not listings:
            break
        explained = explained_listings_by_repository(db, listings)
        pending = []
        for repository_id, candidates in listings.items():
            skip = explained.get(repository_id, set())
            found = next((at for at in candidates if at not in skip), None)
            result[repository_id] = found
            if found is None and len(candidates) == REMOVAL_CANDIDATES:
                pending.append(repository_id)
        page += 1
    return result


def backup_cell(
    db: Session, repository: Repository, spec: dict, starts: list[datetime]
) -> CellStatus:
    """`starts` are the repository's archive start times ascending (the
    series lists flattened), so the archives table is read once per call."""
    jobs = job_evidence(db, repository.id, "backup", spec)
    if not starts:
        return jobs
    cell = CellStatus(
        cell="backup",
        status="completed",
        completed_at=starts[-1],
        running=jobs.running,
        source="archive",
    )
    if jobs.completed_at and jobs.completed_at > starts[-1] and jobs.status in FAILED:
        cell.status, cell.completed_at, cell.source = (
            jobs.status,
            jobs.completed_at,
            jobs.source,
        )
    return cell


def prune_cell(db: Session, repository: Repository, spec: dict) -> CellStatus:
    jobs = job_evidence(db, repository.id, "prune", spec)
    removed_at = prune_removal_evidence(db, [repository.id]).get(repository.id)
    if removed_at is None:
        return jobs
    if jobs.completed_at and jobs.completed_at > removed_at:
        return jobs
    return CellStatus(
        cell="prune",
        status="completed",
        completed_at=removed_at,
        running=jobs.running,
        source="removal",
    )


# -- expectations -------------------------------------------------------------------


def _plan_runs(db: Session, repository_id: int, column: str) -> bool:
    """A backup plan that will run the step for this repository on its
    own: enabled, scheduled (a manual-only plan promises nothing, the
    dispatcher requires schedule_enabled too), dispatchable (availability
    mode or a cron expression: `_next_plan_run` yields no due time for a
    cron plan without one), with this repository's association enabled,
    and the step switched on."""
    return (
        db.query(BackupPlan.id)
        .join(
            BackupPlanRepository, BackupPlanRepository.backup_plan_id == BackupPlan.id
        )
        .filter(
            BackupPlanRepository.repository_id == repository_id,
            BackupPlanRepository.enabled.is_(True),
            BackupPlan.enabled.is_(True),
            BackupPlan.schedule_enabled.is_(True),
            or_(
                BackupPlan.schedule_mode == "availability",
                and_(
                    BackupPlan.cron_expression.isnot(None),
                    BackupPlan.cron_expression != "",
                ),
            ),
            getattr(BackupPlan, column).is_(True),
        )
        .first()
        is not None
    )


def _schedule_runs(db: Session, repository: Repository, column: str) -> bool:
    """A legacy scheduled job that will run the step for this repository,
    resolved the way the scheduler dispatches it: association rows when
    the job has any, else the direct repository_id, else the repository
    path (app/api/schedule.py)."""
    jobs = [
        job
        for job in db.query(ScheduledJob)
        .filter(ScheduledJob.enabled.is_(True), getattr(ScheduledJob, column).is_(True))
        .all()
        # the scheduler dispatches an availability job on its interval and a
        # cron job only with an expression; anything else never runs
        if job.schedule_mode == "availability" or job.cron_expression
    ]
    if not jobs:
        return False
    linked: dict[int, set[int]] = {}
    for job_id, repository_id in db.query(
        ScheduledJobRepository.scheduled_job_id, ScheduledJobRepository.repository_id
    ).filter(ScheduledJobRepository.scheduled_job_id.in_([j.id for j in jobs])):
        linked.setdefault(job_id, set()).add(repository_id)
    for job in jobs:
        if job.id in linked:
            if repository.id in linked[job.id]:
                return True
            continue
        if job.repository_id is not None:
            if job.repository_id == repository.id:
                return True
            continue
        if job.repository and job.repository == repository.path:
            return True
    return False


def _planned(db: Session, repository: Repository, column: str) -> bool:
    """Whether a backup plan or scheduled job of this repository runs the
    step; without one there is nothing to be overdue against. ScheduledJob
    has no run_check_after, so only plans can expect a check."""
    if _plan_runs(db, repository.id, column):
        return True
    return hasattr(ScheduledJob, column) and _schedule_runs(db, repository, column)


def backup_threshold(starts: list[datetime]) -> timedelta:
    """Twice one series' cadence, the fixed default with too few archives."""
    gap = anomalies.median_gap(starts) if len(starts) >= 2 else None
    if gap is None:
        return timedelta(days=anomalies.OVERDUE_THRESHOLD_DAYS["backup"])
    return max(gap * CADENCE_FACTOR, timedelta(hours=1))


def backup_expectation(
    by_series: dict[str, list[datetime]], now: datetime
) -> tuple[timedelta, bool]:
    """(strictest threshold, overdue) across the repository's series. Each
    series is judged against its own cadence; the repository is overdue as
    soon as one of its series is, since every series is a backup someone
    expects. The reported threshold is the strictest one."""
    if not by_series:
        threshold = backup_threshold([])
        return threshold, True
    thresholds = {name: backup_threshold(starts) for name, starts in by_series.items()}
    overdue = any(
        anomalies.overdue_after(starts[-1], now, thresholds[name])
        for name, starts in by_series.items()
    )
    return min(thresholds.values()), overdue


def repository_status(
    db: Session, repository: Repository, *, now: datetime, pro: bool
) -> dict:
    """The status payload: one cell per applicable category."""
    by_series = series_starts(db, repository.id)
    starts = sorted(start for group in by_series.values() for start in group)
    mirror_applies = repository.repository_type == "rclone"
    # Nothing is refreshed for an `off` repository, so an index cell would
    # only ever read as overdue for a state the user chose (spec 6.8).
    index_applies = index_mode_of(repository) != "off"
    cells = []
    for name, spec in CELLS:
        if name == "mirror" and not mirror_applies:
            continue
        if name == "index" and not index_applies:
            continue
        if name == "backup":
            cell = backup_cell(db, repository, spec, starts)
        elif name == "prune":
            cell = prune_cell(db, repository, spec)
        else:
            cell = job_evidence(db, repository.id, name, spec)
        _apply(db, repository, cell, by_series, now=now, pro=pro)
        cells.append(cell.as_dict(now))
    return {"cells": cells, "overdue_available": pro}


def _apply(db, repository, cell, by_series, *, now, pro) -> None:
    fixed = anomalies.OVERDUE_THRESHOLD_DAYS.get(cell.cell)
    overdue: Optional[bool] = None
    if cell.cell == "backup":
        threshold, overdue = backup_expectation(by_series, now)
        cell.threshold_days = max(1, ceil(threshold / timedelta(days=1)))
        expected = True
        # a failed attempt newer than every archive is judged like a run
        if cell.source != "archive":
            overdue = anomalies.overdue_after(cell.completed_at, now, threshold)
    elif cell.cell == "check":
        threshold = timedelta(days=fixed)
        cell.threshold_days = fixed
        # the repository's own check schedule, or a scheduled plan that
        # checks after its backups (the executor runs that check)
        expected = bool(repository.check_schedule_enabled) or _planned(
            db, repository, "run_check_after"
        )
    elif cell.cell in ("prune", "compact"):
        threshold = timedelta(days=fixed)
        cell.threshold_days = fixed
        expected = _planned(db, repository, f"run_{cell.cell}_after")
    else:
        threshold = timedelta(days=fixed)
        cell.threshold_days = fixed
        expected = True
    if not pro or not expected:
        cell.overdue = None
        return
    if overdue is None:
        overdue = anomalies.overdue_after(cell.completed_at, now, threshold)
    cell.overdue = overdue


# -- card metadata row ------------------------------------------------------------


@dataclass
class LastRuns:
    last_prune: Optional[datetime] = None
    last_index: Optional[datetime] = None


def _latest_success_by_repository(
    db: Session, repository_ids: list[int], criterion
) -> dict[int, datetime]:
    """Newest successful operation completion per repository matching
    `criterion` (a kind or a category), one grouped query."""
    rows = (
        db.query(Operation.repository_id, func.max(Operation.completed_at))
        .filter(
            Operation.repository_id.in_(repository_ids),
            criterion,
            Operation.status.in_(SUCCESS_STATUSES),
            Operation.completed_at.isnot(None),
        )
        .group_by(Operation.repository_id)
        .all()
    )
    return {repository_id: completed_at for repository_id, completed_at in rows}


def last_runs(db: Session, repositories: Iterable[Repository]) -> dict[int, LastRuns]:
    """`Last prune` and `Last index` for the repository card's metadata row,
    computed once per page (with more per extra page of removal listings, up
    to REMOVAL_PAGES): prune operations, index operations, the newest listings
    that reported removed archives, the removal listing before each window,
    and the deletion operations that explain some of them.

    Prune follows `prune_cell`'s precedence with successful runs only: the
    newest listing that saw archives disappear without a Borg UI deletion
    explaining it (`prune_removal_evidence`), or a prune completed through
    Borg UI when that is newer. A failed attempt or a dry run does not move
    the value, as neither moves `last_check` or `last_compact`; the status
    route reports the failure. Index is the newest successful operation of
    the `index` category, whatever kind ended the chain.
    """
    ids = [repository.id for repository in repositories]
    result = {repository_id: LastRuns() for repository_id in ids}
    if not ids:
        return result
    prune_ops = _latest_success_by_repository(
        db, ids, and_(Operation.kind == "prune", _not_dry_run())
    )
    index_ops = _latest_success_by_repository(db, ids, Operation.category == "index")
    removals = prune_removal_evidence(db, ids)
    for repository_id in ids:
        job = prune_ops.get(repository_id)
        removed_at = removals.get(repository_id)
        if removed_at is not None and (job is None or removed_at >= job):
            result[repository_id].last_prune = removed_at
        else:
            result[repository_id].last_prune = job
        result[repository_id].last_index = index_ops.get(repository_id)
    return result


# -- storage: the one payload every size reader takes ---------------------------


@dataclass
class StorageSummary:
    """What is stored about a repository's size, in one place (#981): the
    measured size with its provenance and time, Borg's last manifest write,
    the sums over the archive index, and the newest compact statistics.
    Every field can be None: not measured yet, or not reported by this Borg
    version. A reader shows that state rather than a zero. Two more states
    are named explicitly: a size whose `measured_at` is None comes from the
    formatted string (the upgrade's backfill, or a row it did not reach,
    read back on the way out), so its time is unknown; and the archive
    figures are withheld (`archives_consistent` False) while the archive
    rows and `archive_count` disagree, or while no listing has run for the
    repository yet (nothing to be consistent with); `archives_consistent`
    None says they were not computed at all (the list route).
    `latest_archive_files` is the newest archive's file count, not a sum;
    `first_backup_at` and `last_backup_at` span the current archives.
    `original_size_source` names where the source data size came from: the
    repository-level figure Borg reports (`borg1_cache_stats`,
    `compact_stats`), with `original_size_at` the time of the run that
    reported it, or the archive index (`archives`), which is as new as the
    listing and carries no time of its own."""

    size_bytes: Optional[int] = None
    size_source: Optional[str] = None
    measured_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    archives_consistent: Optional[bool] = None
    # whether a listing has ever completed for the repository: tells a
    # withheld figure that will catch up from one nothing has produced,
    # and a settled empty repository from an unlisted one; on every route
    archives_listed: Optional[bool] = None
    original_size: Optional[int] = None
    compressed_size: Optional[int] = None
    deduplicated_size: Optional[int] = None
    original_size_source: Optional[str] = None
    original_size_at: Optional[datetime] = None
    latest_archive_files: Optional[int] = None
    first_backup_at: Optional[datetime] = None
    last_backup_at: Optional[datetime] = None
    compact: Optional[dict] = None
    compact_at: Optional[datetime] = None


def _current_archives(db: Session, repository_ids: list[int]):
    """A filter for the archive rows the newest listing still saw: every
    listing stamps the rows it sees with one `last_seen_at`, so a row an
    earlier listing stamped was reported removed and waits for the next
    archive_sync to drop it (the info dialog's listing reports removals
    without deleting). `archive_count` excludes those rows, and so do the
    sums."""
    newest_seen = (
        db.query(
            Archive.repository_id.label("repository_id"),
            func.max(Archive.last_seen_at).label("last_seen_at"),
        )
        .filter(Archive.repository_id.in_(repository_ids))
        .group_by(Archive.repository_id)
        .subquery()
    )
    return newest_seen, and_(
        Archive.repository_id == newest_seen.c.repository_id,
        Archive.last_seen_at == newest_seen.c.last_seen_at,
    )


def _archive_sums(db: Session, current) -> dict[int, tuple]:
    """Per repository over the current archive rows: the rows, the rows
    whose per-archive info has been filled (`fill_archive_info` writes
    `original_size` and `compressed_size`; a listing alone leaves them
    NULL), the sums over the filled rows, and the stamp those rows carry
    (the listing that last saw them)."""
    newest_seen, current = current
    rows = (
        db.query(
            Archive.repository_id,
            func.count(Archive.id),
            func.count(Archive.original_size),
            func.sum(Archive.original_size),
            func.count(Archive.compressed_size),
            func.sum(Archive.compressed_size),
            func.max(Archive.last_seen_at),
        )
        .join(newest_seen, current)
        .group_by(Archive.repository_id)
        .all()
    )
    return {row[0]: row[1:] for row in rows}


def _archive_span(db: Session, current) -> dict[int, tuple[datetime, datetime]]:
    """The oldest and the newest `start` among each repository's current
    archive rows: the span the backups cover."""
    newest_seen, current = current
    rows = (
        db.query(
            Archive.repository_id, func.min(Archive.start), func.max(Archive.start)
        )
        .join(newest_seen, current)
        .group_by(Archive.repository_id)
        .all()
    )
    return {row[0]: (row[1], row[2]) for row in rows}


def _latest_archive_files(db: Session, current) -> dict[int, int]:
    """`nfiles` of each repository's newest current archive (by start, then
    id), where that archive's info has been filled."""
    newest_seen, current = current
    newest = (
        db.query(Archive.repository_id, func.max(Archive.start).label("start"))
        .join(newest_seen, current)
        .group_by(Archive.repository_id)
        .subquery()
    )
    rows = (
        db.query(Archive.repository_id, Archive.nfiles)
        .join(newest_seen, current)
        .join(
            newest,
            and_(
                Archive.repository_id == newest.c.repository_id,
                Archive.start == newest.c.start,
            ),
        )
        .order_by(Archive.repository_id, Archive.id.desc())
        .all()
    )
    files: dict[int, Optional[int]] = {}
    for repository_id, nfiles in rows:
        # the first row per repository is the newest (highest id among the
        # rows tied on start); a newest archive without its info yet reports
        # nothing rather than an older archive's count
        files.setdefault(repository_id, nfiles)
    return {repository_id: n for repository_id, n in files.items() if n is not None}


# How many of a repository's newest successful operations of a kind are
# read for the figures in their result (a compact's statistics, a stats
# run's source data size). The query keeps only rows whose serialized
# result mentions the key, a textual filter; the window then tolerates a
# row that mentions it without carrying a usable figure. The newest is the
# one wanted.
_RESULT_FIGURE_LOOKBACK = 3


def _listed_repositories(
    db: Session, repository_ids: list[int]
) -> dict[int, Optional[datetime]]:
    """When a listing (`archive_sync`) last completed per repository. A
    repository without one has no archive rows and the count it was
    created with, so "0 rows, count 0" says nothing about its archives;
    with one, the same state is a measurement (an emptied repository).
    The time tells rows a listing has already accounted for from rows it
    has not: `archive_count` is written at the end of a listing, well
    after the rows themselves."""
    rows = (
        db.query(Operation.repository_id, func.max(Operation.completed_at))
        .filter(
            Operation.repository_id.in_(repository_ids),
            Operation.kind == "archive_sync",
            Operation.status.in_(SUCCESS_STATUSES),
        )
        .group_by(Operation.repository_id)
        .all()
    )
    return {repository_id: completed_at for repository_id, completed_at in rows}


def _latest_compact_stats(
    db: Session, repository_ids: list[int]
) -> dict[int, tuple[dict, datetime]]:
    """The statistics of each repository's newest successful compact that
    reported any (`result["stats"]`, Borg 2 `compact --stats`), read from
    the newest few rows per repository (a window, not the whole history)."""
    ranked = (
        db.query(
            Operation.repository_id,
            Operation.result,
            Operation.completed_at,
            func.row_number()
            .over(
                partition_by=Operation.repository_id,
                order_by=(Operation.completed_at.desc(), Operation.id.desc()),
            )
            .label("rank"),
        )
        .filter(
            Operation.repository_id.in_(repository_ids),
            Operation.kind == "compact",
            Operation.status.in_(SUCCESS_STATUSES),
            Operation.completed_at.isnot(None),
            # only rows that carry statistics rank: a run of compacts without
            # them (an agent that predates the report) must not push the
            # newest figure out of the window
            cast(Operation.result, String).like('%"stats"%'),
        )
        .subquery()
    )
    rows = (
        db.query(ranked.c.repository_id, ranked.c.result, ranked.c.completed_at)
        .filter(ranked.c.rank <= _RESULT_FIGURE_LOOKBACK)
        .order_by(ranked.c.repository_id, ranked.c.rank)
        .all()
    )
    found: dict[int, tuple[dict, datetime]] = {}
    for repository_id, result, completed_at in rows:
        if repository_id in found:
            continue
        stats = result.get("stats") if isinstance(result, dict) else None
        if isinstance(stats, dict) and stats:
            found[repository_id] = (stats, completed_at)
    return found


def _borg1_reported_size(result) -> Optional[int]:
    """Borg 1's `cache.stats.total_size`, as `run_stats` filed it."""
    return result.get("original_size") if isinstance(result, dict) else None


def _borg2_reported_size(result) -> Optional[int]:
    """Borg 2's `Source data size`, inside a compact's statistics."""
    stats = result.get("stats") if isinstance(result, dict) else None
    return stats.get("source_size") if isinstance(stats, dict) else None


def _latest_reported_original_size(
    db: Session, repository_ids: list[int], *, kind: str, key: str, read
) -> dict[int, tuple[int, datetime]]:
    """The source data size each repository's newest successful operation
    of `kind` reported, with the time of that run: Borg 1 files it with
    the `stats` run that made the `info` call, Borg 2 with the compact
    that printed it. Only rows whose serialized result mentions `key`
    rank, a textual filter, so a run that reported no figure cannot push
    the last one that did out of the window; the window then tolerates a
    row that mentions the key without carrying a usable figure. The time
    is the figure's own, which a later run without one does not move. 0 is
    a measurement (an emptied repository); anything that is not a whole,
    non-negative number is not a figure."""
    ranked = (
        db.query(
            Operation.repository_id,
            Operation.result,
            Operation.completed_at,
            func.row_number()
            .over(
                partition_by=Operation.repository_id,
                order_by=(Operation.completed_at.desc(), Operation.id.desc()),
            )
            .label("rank"),
        )
        .filter(
            Operation.repository_id.in_(repository_ids),
            Operation.kind == kind,
            Operation.status.in_(SUCCESS_STATUSES),
            Operation.completed_at.isnot(None),
            cast(Operation.result, String).like(f"%{key}%"),
        )
        .subquery()
    )
    rows = (
        db.query(ranked.c.repository_id, ranked.c.result, ranked.c.completed_at)
        .filter(ranked.c.rank <= _RESULT_FIGURE_LOOKBACK)
        .order_by(ranked.c.repository_id, ranked.c.rank)
        .all()
    )
    found: dict[int, tuple[int, datetime]] = {}
    for repository_id, result, completed_at in rows:
        if repository_id in found:
            continue
        value = read(result)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            continue
        found[repository_id] = (value, completed_at)
    return found


def storage_summaries(
    db: Session, repositories: Iterable[Repository], *, archives: bool = True
) -> dict[int, StorageSummary]:
    """One `StorageSummary` per repository. With `archives`, grouped
    queries add the archive sums, the newest compact statistics and the
    newest reported source data size (the detail route); without, only the
    stored columns are read (the list, which is polled and whose card
    shows the size alone). Borg 1's stored size is its deduplicated size
    (`cache.stats`), Borg 2's deduplicated size comes from the newest
    compact statistics; compressed size is a Borg 1 figure (Borg 2 does
    not report it).

    The source data size is never withheld. While the rows the newest
    listing saw all carry their per-archive info they answer for the
    current archive set exactly, and they are taken. Where one of them is
    still waiting for its `borg info` the sum would read as a total it is
    not, and the figure Borg reports for the whole repository answers
    instead: Borg 1 in the `info` call the `stats` operation makes, Borg 2
    in the statistics of a compact. So one unfilled row no longer blanks
    the figure, and the reader is told which of the two it is showing,
    because a compact's figure is only as new as that compact. The
    per-archive figures keep the gate throughout (compressed size, the
    newest archive's files, the backup span)."""
    repos = list(repositories)
    ids = [repository.id for repository in repos]
    if not ids:
        return {}
    if archives:
        current = _current_archives(db, ids)
        sums = _archive_sums(db, current)
        files = _latest_archive_files(db, current)
        spans = _archive_span(db, current)
        compacts = _latest_compact_stats(db, ids)
        # Each version files the figure with a different operation, so only
        # the repositories of that version are asked for: the other query's
        # answer would never be read. The compact rows are asked again
        # rather than taken from `compacts`, which holds the newest
        # statistics of any kind for the dialog: a later compact that
        # reported a repository size without a source data size must not
        # hide the last one that reported one.
        by_version: dict[bool, list[int]] = {}
        for repository in repos:
            by_version.setdefault((repository.borg_version or 1) == 2, []).append(
                repository.id
            )
        reported_original = {}
        for is_borg2, version_ids in by_version.items():
            reported_original.update(
                _latest_reported_original_size(
                    db,
                    version_ids,
                    kind="compact" if is_borg2 else "stats",
                    key='"source_size"' if is_borg2 else '"original_size"',
                    read=_borg2_reported_size if is_borg2 else _borg1_reported_size,
                )
            )
    else:
        sums, files, spans, compacts = {}, {}, {}, {}
        reported_original = {}
    # on every route: the card reads it to tell a settled, empty repository
    # (listed, 0 archives) from one no listing has reached yet
    listed = _listed_repositories(db, ids)
    result: dict[int, StorageSummary] = {}
    for repository in repos:
        (
            count,
            filled_original,
            original,
            filled_compressed,
            compressed,
            rows_seen_at,
        ) = sums.get(repository.id, (0, 0, None, 0, None, None))
        # The rows the newest listing stamped must be the archives it
        # counted: a listing that found nothing stamps nothing, so the rows
        # it reported removed would still read as current, and rows an
        # archive_sync has not dropped yet drift the same way. On a
        # mismatch the archive figures are not reported.
        # `archive_count` also moves without the rows (an agent's own
        # listing, an info sync), so the gate can close between a backup
        # and its `archive_sync`; the flag tells a withheld figure from an
        # absent one. Zero rows against a count of 0 is a measurement only
        # once a listing has run: before that it is the row's initial state.
        # the column is nullable, and a row whose count was never written
        # reads as 0 here and everywhere below: one reading, or the two
        # answers disagree about the same repository
        archive_count = repository.archive_count or 0
        consistent = (
            (count == archive_count and (count > 0 or repository.id in listed))
            if archives
            else None
        )
        compact = compacts.get(repository.id)
        borg2 = (repository.borg_version or 1) == 2
        # An archive count of 0 answers on its own: no archives, no source
        # data. The rows it disagrees with may not be deleted yet (the info
        # dialog's listing leaves them for the next archive_sync), which
        # would otherwise keep a figure alive for archives that are gone. The
        # count is only the newest word while nothing newer contradicts
        # it: rows stamped after that listing (one commits them long
        # before it writes the count, so a repository gaining its first
        # archives is not an empty one), or a repository-level figure from
        # a later run (only a listing writes the count, so an archive
        # created outside this application leaves it behind).
        listed_at = listed.get(repository.id)
        reported = reported_original.get(repository.id)
        emptied = (
            archives
            and listed_at is not None
            and archive_count == 0
            and (rows_seen_at is None or listed_at >= rows_seen_at)
            and (reported is None or listed_at >= reported[1])
        )
        archive_total = (
            0
            if emptied
            else int(original or 0)
            if count > 0 and consistent and filled_original == count
            else None
        )
        original_size_at = None
        if archive_total is not None:
            # as new as the listing that wrote the rows, which the reader
            # already knows; only a figure from elsewhere needs a stamp
            original_size, original_size_source = archive_total, SOURCE_ARCHIVE_SUMS
        else:
            # A row still waiting for its per-archive info leaves the sum
            # unable to answer; the figure Borg reports for the whole
            # repository answers instead, with the time of the run that
            # reported it, because it is not necessarily as new as the
            # size measurement beside it.
            if reported is not None:
                original_size, original_size_at = reported
                original_size_source = (
                    SOURCE_COMPACT_STATS if borg2 else SOURCE_BORG1_CACHE_STATS
                )
            else:
                original_size, original_size_source = None, None
        summary = StorageSummary(
            size_bytes=stored_size_bytes(repository),
            size_source=repository.total_size_source,
            measured_at=repository.total_size_measured_at,
            last_modified=repository.borg_last_modified,
            archives_consistent=consistent,
            archives_listed=repository.id in listed,
            original_size=original_size,
            original_size_source=original_size_source,
            original_size_at=original_size_at,
            latest_archive_files=files.get(repository.id) if consistent else None,
            # the span reads the rows like the sums do, and waits like them
            first_backup_at=spans[repository.id][0]
            if consistent and repository.id in spans
            else None,
            last_backup_at=spans[repository.id][1]
            if consistent and repository.id in spans
            else None,
            compact=compact[0] if compact else None,
            compact_at=compact[1] if compact else None,
        )
        if not borg2:
            # Borg 1's deduplicated size is its stored size when that came
            # from `cache.stats`: a stored column, so both routes carry it
            summary.deduplicated_size = (
                summary.size_bytes
                if repository.total_size_source == SOURCE_BORG1_CACHE_STATS
                else None
            )
        if not archives:
            # the light payload carries the stored columns only; the
            # figures derived from the archive rows and the compact
            # statistics come with the detail
            result[repository.id] = summary
            continue
        if borg2:
            summary.deduplicated_size = (
                compact[0].get("deduplicated_size") if compact else None
            )
        else:
            summary.compressed_size = (
                int(compressed or 0)
                if consistent and filled_compressed == count
                else None
            )
        result[repository.id] = summary
    return result
