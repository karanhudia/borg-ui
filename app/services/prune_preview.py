"""Prune preview (spec 4.4): run Borg's dry run, read its verdicts, join
them to the archive index, re-measure the deletion candidates and, on Pro,
find the files no surviving archive of a series would still hold."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Optional

import structlog
from sqlalchemy.orm import Session

from app.database.models import Archive, Operation, Repository
from app.services.prune_service import _log_message

# One line per archive from `prune --list`, Borg 1.4 and Borg 2 alike:
#   Keeping archive (rule: daily #1):   <name>   Thu, 2026-09-17 15:07:55 [+0530] [<id>]
#   Would prune:                        <name>   Thu, 2026-09-17 15:07:55 [+0530] [<id>]
# The name may hold spaces and brackets, so the id anchors the match at the
# end and the timestamp closes the name. Verified against both binaries on
# 2026-09-17 (plan "What the live Borg binaries print").
_VERDICT_LINE = re.compile(
    r"^(?:Keeping archive \(rule: (?P<rule>[^)]+)\)|Would prune):\s+"
    r"(?P<name>.+?)\s+"
    r"\w{3}, \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?: [+-]\d{4})?\s+"
    r"\[(?P<id>[0-9a-f]{64})\]\s*$"
)
_STREAM_PREFIX = re.compile(r"^\[(?:stdout|stderr)\] ")
logger = structlog.get_logger()


@dataclass(frozen=True)
class Verdict:
    borg_id: str
    name: str
    verdict: str  # "kept" | "deleted"
    rule: Optional[str]


def parse_prune_verdicts(output: str) -> list[Verdict]:
    """The verdict lines of a `prune --list` run, in Borg's order. Raw
    lines, `--log-json` records and the `[stderr] {...}` form the Borg 1
    service stores all parse the same."""
    verdicts: list[Verdict] = []
    for raw in (output or "").splitlines():
        line = _log_message(_STREAM_PREFIX.sub("", raw.strip(), count=1))
        m = _VERDICT_LINE.match(line.strip())
        if not m:
            continue
        rule = m.group("rule")
        verdicts.append(
            Verdict(
                borg_id=m.group("id"),
                name=m.group("name"),
                verdict="kept" if rule is not None else "deleted",
                rule=rule,
            )
        )
    return verdicts


@dataclass(frozen=True)
class Retention:
    keep_hourly: int = 0
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6
    keep_quarterly: int = 0
    keep_yearly: int = 1
    keep_within: Optional[str] = None

    def as_params(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def has_rule(self) -> bool:
        """Borg refuses a prune with no keep rule at all."""
        return any(
            getattr(self, k) > 0
            for k in (
                "keep_hourly",
                "keep_daily",
                "keep_weekly",
                "keep_monthly",
                "keep_quarterly",
                "keep_yearly",
            )
        ) or bool(self.keep_within)


async def run_prune_dry_run(
    db: Session,
    repository: Repository,
    retention: Retention,
    *,
    user_id: Optional[int],
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
) -> tuple[Operation, str]:
    """Borg's own dry run, inline, on an operation row created `running`
    and closed here (the path the prune route has always taken). Returns
    the finished row and its log text."""
    from app.services.operations.job_facade import MaintenanceJobFacade
    from app.api.maintenance_jobs import read_job_logs
    from app.core.borg_router import BorgRouter
    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    operation = start_inline_maintenance(
        db,
        repository,
        "prune",
        params={**retention.as_params(), "dry_run": True, "scheduled_prune": False},
        user_id=user_id,
        run_id=run_id,
        depends_on_id=depends_on_id,
        # the page's own dry run; a step of a run inherits the run's trigger
        trigger="preview",
    )
    prune_kwargs = (
        {"keep_within": retention.keep_within}
        if retention.keep_within is not None
        else {}
    )
    try:
        await BorgRouter(repository).prune(
            operation.id,
            retention.keep_hourly,
            retention.keep_daily,
            retention.keep_weekly,
            retention.keep_monthly,
            retention.keep_quarterly,
            retention.keep_yearly,
            True,
            **prune_kwargs,
        )
    except Exception as exc:
        # The row was created `running`; a step that raised never closed it.
        await fail_inline_maintenance(db, operation, exc)
        raise
    db.refresh(operation)
    # A dry run changed nothing, so it gets no follow-up chain.
    finish_inline_maintenance(db, operation, enqueue_followups=False)
    view = MaintenanceJobFacade(db, operation)
    log = read_job_logs(view, fallback_to_logs=True, log_save_policy="all_jobs")
    return operation, log


from datetime import datetime

from app.services.operations.executors.index import (
    _prepare_repository_borg_env,
    fill_archive_info,
)
from app.services.operations.repository_status import (
    pending_removed_ids,
    storage_summaries,
)
from app.utils.borg_env import cleanup_temp_key_file

# Candidates re-measured synchronously before the preview answers (spec
# 4.4 step 3). Beyond it, or when a measurement fails, the stored values
# stand and `partial_measure` is reported.
MEASURE_CAP = 50


@dataclass
class PreviewArchive:
    id: Optional[int]
    borg_id: str
    name: str
    series: Optional[str]
    start: Optional[datetime]
    verdict: str
    rule: Optional[str]
    deduplicated_size: Optional[int]
    stats_measured_at: Optional[datetime]


def join_verdicts(
    db: Session, repository: Repository, verdicts: list[Verdict]
) -> list[PreviewArchive]:
    """Each verdict line joined to its `archives` row by Borg id (Borg 2
    series share a name). A line whose id the index does not hold, or whose
    row the newest listing reported removed, keeps Borg's name and verdict
    with no row behind it."""
    ids = [v.borg_id for v in verdicts]
    rows: dict[str, Archive] = {}
    removed = pending_removed_ids(db, repository.id)
    for i in range(0, len(ids), 500):
        for row in (
            db.query(Archive)
            .filter(
                Archive.repository_id == repository.id,
                Archive.borg_id.in_(ids[i : i + 500]),
            )
            .all()
        ):
            if row.id not in removed:
                rows[row.borg_id] = row
    out: list[PreviewArchive] = []
    for v in verdicts:
        row = rows.get(v.borg_id)
        out.append(
            PreviewArchive(
                id=row.id if row else None,
                borg_id=v.borg_id,
                name=row.name if row else v.name,
                series=row.series if row else None,
                start=row.start if row else None,
                verdict=v.verdict,
                rule=v.rule,
                deduplicated_size=row.deduplicated_size if row else None,
                stats_measured_at=row.stats_measured_at if row else None,
            )
        )
    return out


async def remeasure_candidates(
    db: Session, repository: Repository, candidates: list[Archive]
) -> bool:
    """Fresh `deduplicated_size` for the deletion candidates, oldest first,
    up to MEASURE_CAP (spec 4.1: the preview re-measures synchronously).
    Returns True when the cap left some candidates on their stored value.
    `fill_archive_info` commits and stamps `stats_measured_at` itself."""
    if not candidates:
        return False
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        filled = await fill_archive_info(
            db, repository, candidates, env, limit=MEASURE_CAP
        )
    except Exception as exc:
        # A busy repository (another job took the lock after the dry run)
        # or an agent that stopped answering: the stored values stand and
        # the preview says so, rather than failing after Borg's verdicts
        # were already in hand.
        logger.warning(
            "prune preview re-measure abandoned, stored sizes used",
            repository_id=repository.id,
            error=str(exc),
        )
        db.rollback()
        filled = 0
    finally:
        cleanup_temp_key_file(temp_key_file)
    return filled < len(candidates)


def freed_at_least(candidates: list[Archive]) -> int:
    """Lower bound: chunks shared only among the candidates are in nobody's
    deduplicated_size (Appendix B)."""
    return sum(
        a.deduplicated_size for a in candidates if a.deduplicated_size is not None
    )


def footprint(db: Session, repository: Repository) -> Optional[int]:
    """The repository's stored size (the `storage` payload of #1030)."""
    summary = storage_summaries(db, [repository], archives=False).get(repository.id)
    return summary.size_bytes if summary else None


from collections import defaultdict

from sqlalchemy import distinct

from app.database.models import ArchiveChange
from app.services.operations.executors.history import SIZE_LOOKUP_CHUNK

TOP_LOST = 200
TOP_FOLDERS = 20
_FOLDER_DEPTH = 3


def _folder_of(path: str) -> str:
    """The rollup key: the parent directory, at most _FOLDER_DEPTH deep.
    Borg paths have no leading slash."""
    parts = path.split("/")[:-1]
    return "/".join(parts[:_FOLDER_DEPTH]) or "/"


def _candidate_paths(db: Session, ids: list[int], removed_only: bool) -> set[str]:
    paths: set[str] = set()
    for i in range(0, len(ids), SIZE_LOOKUP_CHUNK):
        q = db.query(distinct(ArchiveChange.path)).filter(
            ArchiveChange.archive_id.in_(ids[i : i + SIZE_LOOKUP_CHUNK])
        )
        q = q.filter(
            ArchiveChange.change == "removed"
            if removed_only
            else ArchiveChange.change != "summary"
        )
        paths.update(p for (p,) in q.all())
    return paths


def _lost_in_series(
    db: Session, archives: list[Archive], deleted_ids: set[int]
) -> list[dict]:
    """The walk described in the phase 3 plan, Task 4. `archives` are the
    series' rows ordered by (start, id)."""
    ids = [a.id for a in archives]
    newest_deleted = archives[-1].id in deleted_ids
    candidates = _candidate_paths(db, ids, removed_only=not newest_deleted)
    if not candidates:
        return []
    # ponytail: the candidate map is bounded by the paths ever removed in
    # the series (or every path, when the whole series goes). If that ever
    # fails on memory, page the candidates and repeat the walk per page.
    # state: path -> (present, size, last_present_archive, removing_archive)
    state: dict[
        str, tuple[bool, Optional[int], Optional[Archive], Optional[Archive]]
    ] = {}
    dirty: set[str] = set()
    first_sweep = True
    previous: Optional[Archive] = None
    for archive in archives:
        rows = (
            db.query(
                ArchiveChange.path,
                ArchiveChange.change,
                ArchiveChange.size_before,
                ArchiveChange.size_after,
            )
            .filter(
                ArchiveChange.archive_id == archive.id,
                ArchiveChange.change != "summary",
            )
            .yield_per(1000)
        )
        for path, change, size_before, size_after in rows:
            if path not in candidates:
                continue
            dirty.add(path)
            if change == "removed":
                # "Last held by": the archive before the removing one in
                # series order (state carries across archives without rows).
                state[path] = (False, size_before, previous, archive)
            else:
                state[path] = (True, size_after, archive, None)
        if archive.id not in deleted_ids:
            for path in list(candidates if first_sweep else dirty):
                present = state.get(path, (False,))[0]
                if present:
                    candidates.discard(path)
                    state.pop(path, None)
            first_sweep = False
            dirty.clear()
        previous = archive
    lost = []
    for path in candidates:
        present, size, held, _ = state.get(path, (False, None, None, None))
        if present:
            # Only reachable when no archive of the series survives: a path
            # still present at the end was held by every archive since it
            # was written, so the newest one is the honest "last held by".
            held = archives[-1]
        lost.append({"path": path, "size": size, "held": held})
    return lost


FileKey = tuple[str, Optional[int]]


def _file_key(path: str, size: Optional[int]) -> Optional[FileKey]:
    """What the index can say two paths have in common: the file name and
    its size. A source mounted at a new prefix backs up every file under a
    new path, which is how a whole tree looks lost when nothing is. None
    for a file of unknown size: a name alone is not identity, and a wrong
    match would drop a genuinely lost file from the totals."""
    if size is None:
        return None
    return (path.rsplit("/", 1)[-1], size)


def _same_file_moved(lost: str, survivor: str) -> bool:
    """Whether a surviving path is the same file under a new prefix: one
    path is the tail of the other, whole segments only. Name and size alone
    would let an unrelated README of the same length hide a real loss."""
    return survivor.endswith("/" + lost) or lost.endswith("/" + survivor)


def _held_by_survivors(
    db: Session,
    series_rows: list[list[Archive]],
    deleted_ids: set[int],
    lost: list[dict],
) -> tuple[set[str], dict[FileKey, set[str]], list[int]]:
    """What the surviving archives of the given series still hold of the
    lost rows, by replaying each series' changes in order and reading the
    state at every archive: the lost paths held as they are, and for the
    rest a file of the same name and size held under another path. Also
    returns the archives whose index is missing while a path is still in
    question, since those could hold it too."""
    open_paths = {f["path"] for f in lost}
    open_keys = {k for f in lost if (k := _file_key(f["path"], f["size"])) is not None}
    held: set[str] = set()
    copies: dict[FileKey, set[str]] = defaultdict(set)
    unindexed: list[int] = []
    for archives in series_rows:
        if not open_paths and not open_keys:
            break
        present: set[str] = set()
        # key -> paths present under it, so a removal of one copy keeps another
        present_keys: dict[FileKey, set[str]] = defaultdict(set)
        for archive in archives:
            if archive.history_state != "indexed":
                unindexed.append(archive.id)
            rows = (
                db.query(
                    ArchiveChange.path,
                    ArchiveChange.change,
                    ArchiveChange.size_before,
                    ArchiveChange.size_after,
                )
                .filter(
                    ArchiveChange.archive_id == archive.id,
                    ArchiveChange.change != "summary",
                )
                .yield_per(1000)
            )
            for path, change, size_before, size_after in rows:
                if path in open_paths:
                    if change == "removed":
                        present.discard(path)
                    else:
                        present.add(path)
                if change == "modified":
                    # the file no longer holds its old size: drop that key,
                    # or this archive looks like it holds both versions
                    stale = _file_key(path, size_before)
                    if stale is not None and stale in open_keys:
                        present_keys[stale].discard(path)
                key = _file_key(
                    path, size_before if change == "removed" else size_after
                )
                if key is not None and key in open_keys:
                    if change == "removed":
                        present_keys[key].discard(path)
                    else:
                        present_keys[key].add(path)
            if archive.id in deleted_ids:
                # its changes shape the state, its contents go
                continue
            # a survivor: what it holds is safe
            held.update(present)
            open_paths -= present
            for key, paths in present_keys.items():
                if paths and key in open_keys:
                    # every copy this survivor holds, since one surviving
                    # file only accounts for one lost file, not for every
                    # path that happens to share its name and size
                    copies[key].update(paths)
                    open_keys.discard(key)
            if not open_paths and not open_keys:
                break
    return held, copies, unindexed


def lost_files(
    db: Session,
    repository: Repository,
    archives_by_series: dict[str, list[Archive]],
    deleted_ids: set[int],
) -> dict:
    """Spec 4.4 step 5, from the history index only: the walk per series
    finds the paths its survivors no longer hold, then the untouched series
    are replayed for those paths, since a renamed plan leaves the newest
    archives in a different series from the ones being deleted."""
    unindexed: list[int] = []
    # path -> (last held start, row): a path two series both lose is one
    # file, reported once, under the archive that held it last
    newest: dict[str, tuple] = {}
    untouched: list[list[Archive]] = []
    for series, archives in archives_by_series.items():
        if not any(a.id in deleted_ids for a in archives):
            untouched.append(archives)
            continue
        unindexed.extend(a.id for a in archives if a.history_state != "indexed")
        for item in _lost_in_series(db, archives, deleted_ids):
            held = item["held"]
            row = {
                "path": item["path"],
                "size": item["size"],
                "series": series,
                "last_held_archive_id": held.id if held else None,
                "last_held_archive_name": held.name if held else None,
            }
            when = (held.start, held.id) if held else None
            seen = newest.get(row["path"])
            if seen is None or (
                when is not None and (seen[0] is None or when > seen[0])
            ):
                newest[row["path"]] = (when, row)
    found = [row for _, row in newest.values()]
    # The same file under another path is not lost: the survivors of every
    # series are read for the lost paths themselves and for a file of the
    # same name and size. Those go under `moved`, out of the lost totals.
    moved: list[dict] = []
    if found:
        # a touched series' own survivors were read by the walk for the path,
        # but not for a copy of it, so they are replayed here as well
        held, copies, unindexed_elsewhere = _held_by_survivors(
            db, list(archives_by_series.values()), deleted_ids, found
        )
        unindexed.extend(unindexed_elsewhere)
        lost = []
        for f in found:
            if f["path"] in held:
                continue
            key = _file_key(f["path"], f["size"])
            others = sorted(
                p
                for p in ((copies.get(key) or set()) - {f["path"]})
                if _same_file_moved(f["path"], p)
            )
            if others:
                # spend the copy: it cannot stand in for a second lost file
                copies[key].discard(others[0])
                moved.append(f)
            else:
                lost.append(f)
        found = lost
    unindexed = sorted(set(unindexed))
    by_size = lambda f: (-(f["size"] or 0), f["path"])  # noqa: E731
    found.sort(key=by_size)
    folders: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for f in found:
        entry = folders[_folder_of(f["path"])]
        entry[0] += 1
        entry[1] += f["size"] or 0
    by_folder = sorted(
        ({"folder": k, "count": v[0], "size": v[1]} for k, v in folders.items()),
        key=lambda x: (-x["size"], x["folder"]),
    )[:TOP_FOLDERS]
    return {
        "incomplete": bool(unindexed),
        "unindexed_archive_ids": unindexed,
        "total_count": len(found),
        "total_size": sum(f["size"] or 0 for f in found),
        "top": found[:TOP_LOST],
        "by_folder": by_folder,
        "moved_count": len(moved),
        "moved_size": sum(f["size"] or 0 for f in moved),
    }


from app.services.operations.followups import (
    HISTORY_AVAILABLE,
    history_capability,
    history_enabled,
)


def lost_size_estimate(
    db: Session, repository: Repository, candidates: list[Archive]
) -> Optional[int]:
    """The logical size of the files no kept archive holds once `candidates`
    are deleted. Compression and deduplication mean the storage this frees
    is at most this, never exactly it, so it belongs next to
    `freed_at_least`, not in its place. None without the history index,
    and None while the index is incomplete: an unindexed archive on either
    side moves the total both ways, so it is no longer a ceiling."""
    if (
        not history_enabled(db)
        or history_capability(db, repository) != HISTORY_AVAILABLE
    ):
        return None
    lost = lost_files(
        db,
        repository,
        archives_by_series(db, repository),
        deleted_ids={a.id for a in candidates},
    )
    return None if lost["incomplete"] else lost["total_size"]


def archives_by_series(db: Session, repository: Repository) -> dict[str, list[Archive]]:
    removed = pending_removed_ids(db, repository.id)
    q = db.query(Archive).filter(Archive.repository_id == repository.id)
    if removed:
        q = q.filter(Archive.id.notin_(removed))
    out: dict[str, list[Archive]] = {}
    for a in q.order_by(
        Archive.series.asc(), Archive.start.asc(), Archive.id.asc()
    ).all():
        out.setdefault(a.series, []).append(a)
    return out


class DryRunFailed(Exception):
    def __init__(self, log: str):
        super().__init__("prune dry run failed")
        self.log = log


@dataclass
class CandidateResult:
    operation: Operation
    log: str
    joined: list[PreviewArchive]
    candidates: list[Archive]
    partial_measure: bool
    freed_at_least: int
    kept_count: int
    deleted_count: int


async def run_candidate(
    db: Session,
    repository: Repository,
    retention: Retention,
    *,
    user_id: Optional[int],
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
    remeasure: bool = True,
) -> CandidateResult:
    """Spec 4.4 steps 1 to 4: dry run, verdict join, candidate re-measure,
    freed lower bound. Shared by the preview page and the comparison
    (spec 4.5), which passes `remeasure=False`: it runs after a backup,
    and nothing is re-measured after a backup (Appendix B); a candidate
    never measured then counts as partial. Raises DryRunFailed when Borg's
    dry run did not complete."""
    operation, log = await run_prune_dry_run(
        db,
        repository,
        retention,
        user_id=user_id,
        run_id=run_id,
        depends_on_id=depends_on_id,
    )
    if operation.status not in ("completed", "completed_with_warnings"):
        raise DryRunFailed(log)
    joined = join_verdicts(db, repository, parse_prune_verdicts(log))
    by_id = {
        a.id: a for rows in archives_by_series(db, repository).values() for a in rows
    }
    candidates = [
        by_id[p.id] for p in joined if p.verdict == "deleted" and p.id in by_id
    ]
    if remeasure:
        partial = await remeasure_candidates(db, repository, candidates)
    else:
        partial = any(a.stats_measured_at is None for a in candidates)
    for p in joined:
        row = by_id.get(p.id) if p.id is not None else None
        if row is not None:
            p.deduplicated_size = row.deduplicated_size
            p.stats_measured_at = row.stats_measured_at
    return CandidateResult(
        operation=operation,
        log=log,
        joined=joined,
        candidates=candidates,
        partial_measure=partial,
        freed_at_least=freed_at_least(candidates),
        kept_count=sum(1 for p in joined if p.verdict == "kept"),
        deleted_count=sum(1 for p in joined if p.verdict == "deleted"),
    )


def assemble_preview(
    db: Session,
    repository: Repository,
    joined: list[PreviewArchive],
    *,
    operation_id: Optional[int],
    log: str,
    freed: int,
    partial: bool,
) -> dict:
    """Spec 4.4 step 5: the page's payload from an already-joined verdict
    list. Shared by the dry run and by a stored comparison candidate, so a
    row read back reads exactly as the run that produced it."""
    pro = history_enabled(db)  # commits; before the archive rows load
    before = footprint(db, repository)
    deleted_ids = {p.id for p in joined if p.verdict == "deleted" and p.id is not None}
    capability = history_capability(db, repository)
    lost: dict = {"available": False, "capability": capability}
    if pro and capability == HISTORY_AVAILABLE:
        lost = {
            "available": True,
            "capability": capability,
            **lost_files(
                db,
                repository,
                archives_by_series(db, repository),
                deleted_ids=deleted_ids,
            ),
        }
    joined.sort(key=lambda p: (p.start is None, p.start or datetime.min, p.id or 0))
    return {
        "operation_id": operation_id,
        "archives": [
            {
                "id": p.id,
                "borg_id": p.borg_id,
                "name": p.name,
                "series": p.series,
                "start": p.start,
                "verdict": p.verdict,
                "rule": p.rule,
                "deduplicated_size": p.deduplicated_size,
                "stats_measured_at": p.stats_measured_at,
                "stale": p.id is not None and p.stats_measured_at is None,
            }
            for p in joined
        ],
        "deleted_count": sum(1 for p in joined if p.verdict == "deleted"),
        "kept_count": sum(1 for p in joined if p.verdict == "kept"),
        "freed_at_least": freed,
        "partial_measure": partial,
        "footprint_before": before,
        "footprint_after_at_most": max(before - freed, 0)
        if before is not None
        else None,
        "lost_files": lost,
        "log": log,
    }


def preview_from_verdicts(
    db: Session,
    repository: Repository,
    verdicts: list[Verdict],
    *,
    operation_id: Optional[int],
) -> dict:
    """A stored comparison candidate as the preview page's payload. Borg is
    not run: the verdicts are what it said, and the sizes, series and lost
    files are joined from the index as it stands now. Nothing is re-measured
    (as in the comparison itself), so a candidate never measured counts as
    partial."""
    joined = join_verdicts(db, repository, verdicts)
    by_id = {
        a.id: a for rows in archives_by_series(db, repository).values() for a in rows
    }
    candidates = [
        by_id[p.id] for p in joined if p.verdict == "deleted" and p.id in by_id
    ]
    return assemble_preview(
        db,
        repository,
        joined,
        operation_id=operation_id,
        log="",
        freed=freed_at_least(candidates),
        partial=any(a.stats_measured_at is None for a in candidates),
    )


async def build_preview(
    db: Session,
    repository: Repository,
    retention: Retention,
    *,
    user_id: Optional[int],
    run_id: Optional[str] = None,
) -> dict:
    """Spec 4.4 steps 1 to 5 in order. Raises DryRunFailed when Borg's dry
    run did not complete, with the log attached. `run_id` groups the dry runs
    of one visit to the preview page under one run in the timeline."""
    r = await run_candidate(db, repository, retention, user_id=user_id, run_id=run_id)
    return assemble_preview(
        db,
        repository,
        r.joined,
        operation_id=r.operation.id,
        log=r.log,
        freed=r.freed_at_least,
        partial=r.partial_measure,
    )


def retention_defaults(db: Session, repository: Repository) -> dict:
    """What the preview page prefills: the plan's retention, else the last
    real manual prune's, else the dialog's defaults."""
    from app.services.operations.series import _plans_for

    plans = sorted(
        (
            p
            for p in _plans_for(db, repository, active_links_only=True)
            if p.enabled and p.run_prune_after
        ),
        key=lambda p: p.name or "",
    )
    if plans:
        p = plans[0]
        return {
            "source": "plan",
            "plan_name": p.name,
            "keep_hourly": p.prune_keep_hourly or 0,
            "keep_daily": p.prune_keep_daily or 0,
            "keep_weekly": p.prune_keep_weekly or 0,
            "keep_monthly": p.prune_keep_monthly or 0,
            "keep_quarterly": p.prune_keep_quarterly or 0,
            "keep_yearly": p.prune_keep_yearly or 0,
            "keep_within": p.prune_keep_within or None,
        }
    last = (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "prune",
            Operation.trigger == "manual",
        )
        .order_by(Operation.id.desc())
        .all()
    )
    for op in last:
        params = op.params or {}
        if params.get("dry_run"):
            continue
        base = Retention().as_params()
        base.update(
            {k: params[k] for k in base if k in params and params[k] is not None}
        )
        return {"source": "last_prune", "plan_name": None, **base}
    return {"source": "default", "plan_name": None, **Retention().as_params()}
