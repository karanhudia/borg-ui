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
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

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
from app.services.operations.legacy_status import latest_legacy_terminal
from app.services.operations.vocab import SUCCESS_STATUSES

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


def _operations(db: Session, repository_id: int, spec: dict):
    q = db.query(Operation).filter(Operation.repository_id == repository_id)
    if "kinds" in spec:
        return q.filter(Operation.kind.in_(spec["kinds"]))
    return q.filter(Operation.category == spec["category"])


def job_evidence(db: Session, repository_id: int, cell: str, spec: dict) -> CellStatus:
    """The newest terminal job row for a cell, operations first, legacy
    tables until phase 9 removes them; plus whether one is running."""
    q = _operations(db, repository_id, spec)
    running = q.filter(Operation.status == "running").first() is not None
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
    legacy = latest_legacy_terminal(db, repository_id, cell)
    if legacy and (result.completed_at is None or legacy[1] > result.completed_at):
        result.status, result.completed_at, result.source = (
            legacy[0],
            legacy[1],
            "legacy",
        )
    return result


def pending_removed_ids(db: Session, repository_id: int) -> set[int]:
    """Archive rows the newest successful archive_sync reported removed and
    history_merge has not deleted yet: archive_sync never deletes (spec
    6.4), so between the two the rows are still in the table. The same
    exclusion `write_repository_archive_columns` applies to last_backup."""
    row = (
        db.query(Operation.result)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "archive_sync",
            Operation.status.in_(SUCCESS_STATUSES),
            Operation.completed_at.isnot(None),
        )
        .order_by(Operation.completed_at.desc())
        .first()
    )
    if row is None:
        return set()
    return set((row[0] or {}).get("removed_archive_ids") or [])


def series_starts(
    db: Session, repository_id: int, exclude: set[int] = frozenset()
) -> dict[str, list[datetime]]:
    """Archive start times per series, each ascending. Archives without a
    series form one group of their own: a cadence is a property of a
    series, and timestamps of different series interleave (two nightly
    hosts a minute apart look hourly when mixed).

    Bounded to the newest CADENCE_SAMPLE archives per series: the cadence
    reads no further back and the newest archive is among them, while the
    strip polls this every 30 s per card, so a long hourly history is not
    scanned on every poll."""
    rank = (
        func.row_number()
        .over(
            partition_by=Archive.series,
            order_by=(Archive.start.desc(), Archive.id.desc()),
        )
        .label("rank")
    )
    ranked = db.query(
        Archive.series.label("series"), Archive.start.label("start"), rank
    ).filter(Archive.repository_id == repository_id)
    if exclude:
        ranked = ranked.filter(Archive.id.notin_(list(exclude)))
    ranked = ranked.subquery()
    result: dict[str, list[datetime]] = {}
    for series, start in (
        db.query(ranked.c.series, ranked.c.start)
        .filter(ranked.c.rank <= anomalies.CADENCE_SAMPLE)
        .order_by(ranked.c.start.asc())
        .all()
    ):
        result.setdefault(series or "", []).append(start)
    return result


def latest_removal(db: Session, repository_id: int) -> Optional[datetime]:
    """When archives were last seen to disappear: the newest successful
    archive_sync whose result lists removed archives. An upper bound, since
    the removal happened between that listing and the one before. A sync
    the runner marked cancelled keeps its listing but gets no follow-ups,
    so its removals are not applied and the next successful listing
    reports them again."""
    # Newest first, streamed in pages and stopped at the first listing with
    # removals: the JSON result is only loaded up to that row. A SQL-side
    # filter on the JSON list would need dialect-specific functions (SQLite
    # and PostgreSQL spell json_array_length differently); retention bounds
    # how far a repository without removals is scanned.
    rows = (
        db.query(Operation.completed_at, Operation.result)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "archive_sync",
            Operation.status.in_(SUCCESS_STATUSES),
            Operation.completed_at.isnot(None),
        )
        .order_by(Operation.completed_at.desc())
        .yield_per(100)
    )
    for completed_at, result in rows:
        if (result or {}).get("removed_archive_ids"):
            return completed_at
    return None


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
    removed_at = latest_removal(db, repository.id)
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
    """The strip payload: one cell per applicable category."""
    pending = pending_removed_ids(db, repository.id)
    by_series = series_starts(db, repository.id, pending)
    starts = sorted(start for group in by_series.values() for start in group)
    mirror_applies = repository.repository_type == "rclone"
    cells = []
    for name, spec in CELLS:
        if name == "mirror" and not mirror_applies:
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
