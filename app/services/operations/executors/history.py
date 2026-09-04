"""History executors: history_index and history_merge (spec 8.3, 8.4, 6.7).

history_index streams `borg diff` per (predecessor, archive) pair, or a
full `borg list` for the first archive of a series, drops excluded paths,
resolves absolute sizes for modified files from the last known size in the
series, caps rows per archive, and writes each archive in one transaction.
history_merge folds a removed archive's rows into its successor.
"""

import asyncio
import re
from collections import Counter
from typing import Iterable, Optional

import structlog
from sqlalchemy.orm import Session

from app.api.repositories import _prepare_repository_borg_env
from app.config import settings
from app.core.borg_diff import ChangeRecord, parse_diff_line, parse_list_line
from app.core.borg_router import BorgRouter
from app.database.models import Archive, ArchiveChange, Operation, Repository, utc_now
from app.services.operations import executors
from app.services.operations.executors.index import _load_repository
from app.services.operations.followups import history_enabled
from app.services.operations.history_fold import (
    change_to_row_dict,
    fold_pair,
    rows_to_changes,
)
from app.services.operations.runner import Outcome
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.repository_executor import is_agent_executor
from app.utils.borg_env import cleanup_temp_key_file

logger = structlog.get_logger()

BATCH_SIZE = 5000
SUMMARY_DEPTH = 3
SIZE_LOOKUP_CHUNK = 500
# borg exits 1 for warnings; the diff is still complete
BORG_OK_EXIT_CODES = (0, 1)


class OperationCancelled(Exception):
    pass


# -- excludes -------------------------------------------------------------------


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a glob with `**` (any depth), `*` (one segment), `?` into a
    regex anchored to the whole path. A leading `**/` matches zero or more
    directories so `**/.cache/**` covers `.cache/x` at the root too."""
    out = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(f"^{out}$")


def compile_excludes(patterns: Optional[list[str]]) -> list[re.Pattern]:
    return [glob_to_regex(p) for p in (patterns or []) if p]


def is_excluded(path: str, compiled: list[re.Pattern]) -> bool:
    return any(rx.match(path) for rx in compiled)


def summary_prefix(path: str) -> str:
    return "/".join(path.split("/")[:SUMMARY_DEPTH])


# -- row collection -------------------------------------------------------------


class RowCollector:
    """Rows for one archive with the spec 6.7 cap applied on the fly."""

    def __init__(self, archive_id: int, max_rows: int):
        self.archive_id = archive_id
        self.max_rows = max_rows
        self.detail: list[dict] = []
        self.overflow: Counter = Counter()
        self.count = 0

    def add(
        self,
        record: ChangeRecord,
        size_before: Optional[int],
        size_after: Optional[int],
    ) -> None:
        self.count += 1
        if len(self.detail) < self.max_rows:
            self.detail.append(
                {
                    "archive_id": self.archive_id,
                    "path": record.path,
                    "change": record.change,
                    "size_before": size_before,
                    "size_after": size_after,
                    "mode_changed": record.mode_changed,
                    "owner_changed": record.owner_changed,
                    "summary_count": None,
                }
            )
        else:
            self.overflow[summary_prefix(record.path)] += 1

    @property
    def truncated(self) -> bool:
        return bool(self.overflow)

    def summary_rows(self) -> list[dict]:
        return [
            {
                "archive_id": self.archive_id,
                "path": prefix,
                "change": "summary",
                "size_before": None,
                "size_after": None,
                "mode_changed": False,
                "owner_changed": False,
                "summary_count": n,
            }
            for prefix, n in sorted(self.overflow.items())
        ]


def known_sizes(
    db: Session, repository_id: int, series: str, before_start, paths: Iterable[str]
) -> dict[str, int]:
    """Last known size of each path in earlier archives of the series."""
    paths = list(dict.fromkeys(paths))
    result: dict[str, int] = {}
    for i in range(0, len(paths), SIZE_LOOKUP_CHUNK):
        chunk = paths[i : i + SIZE_LOOKUP_CHUNK]
        rows = (
            db.query(ArchiveChange.path, ArchiveChange.size_after)
            .join(Archive, Archive.id == ArchiveChange.archive_id)
            .filter(
                Archive.repository_id == repository_id,
                Archive.series == series,
                Archive.start < before_start,
                ArchiveChange.path.in_(chunk),
                ArchiveChange.change.in_(("added", "modified")),
                ArchiveChange.size_after.isnot(None),
            )
            .order_by(Archive.start.desc(), Archive.id.desc())
            .all()
        )
        for path, size in rows:
            result.setdefault(path, size)
    return result


# -- archive neighbours ---------------------------------------------------------


def predecessor_of(db: Session, archive: Archive) -> Optional[Archive]:
    return (
        db.query(Archive)
        .filter(
            Archive.repository_id == archive.repository_id,
            Archive.series == archive.series,
            Archive.start < archive.start,
        )
        .order_by(Archive.start.desc(), Archive.id.desc())
        .first()
    )


def successor_of(db: Session, archive: Archive) -> Optional[Archive]:
    return (
        db.query(Archive)
        .filter(
            Archive.repository_id == archive.repository_id,
            Archive.series == archive.series,
            Archive.start > archive.start,
        )
        .order_by(Archive.start.asc(), Archive.id.asc())
        .first()
    )


def archive_ref(repository: Repository, archive: Archive) -> str:
    return (
        f"aid:{archive.borg_id}"
        if (repository.borg_version or 1) == 2
        else archive.name
    )


# -- collecting one archive -----------------------------------------------------


async def collect_changes(
    ctx,
    db: Session,
    repository: Repository,
    archive: Archive,
    predecessor: Optional[Archive],
    env: dict,
    excludes: list[re.Pattern],
    max_rows: int,
) -> RowCollector:
    router = BorgRouter(repository)
    if predecessor is None:
        stream = router.list_archive_lines(archive_ref(repository, archive), env=env)
        parser = parse_list_line
    else:
        stream = router.diff_archives(
            archive_ref(repository, predecessor),
            archive_ref(repository, archive),
            env=env,
        )
        parser = parse_diff_line
    collector = RowCollector(archive.id, max_rows)
    pending_modified: list[ChangeRecord] = []

    def flush_modified() -> None:
        if not pending_modified:
            return
        sizes = known_sizes(
            db,
            repository.id,
            archive.series,
            archive.start,
            (r.path for r in pending_modified),
        )
        for rec in pending_modified:
            before = sizes.get(rec.path)
            after = before + rec.size_delta if before is not None else None
            collector.add(rec, before, after)
        pending_modified.clear()

    async for line in stream:
        if ctx.cancelled():
            await stream.close()
            raise OperationCancelled()
        rec = parser(line)
        if rec is None or rec.is_directory or is_excluded(rec.path, excludes):
            continue
        if rec.change == "modified" and rec.size_delta is not None:
            pending_modified.append(rec)
            if len(pending_modified) >= SIZE_LOOKUP_CHUNK:
                flush_modified()
        else:
            collector.add(rec, rec.size_before, rec.size_after)
    flush_modified()
    if stream.return_code not in BORG_OK_EXIT_CODES:
        raise RuntimeError(
            f"borg exited {stream.return_code}: {(stream.stderr or '').strip()[-500:]}"
        )
    return collector


def write_archive_rows(db: Session, archive: Archive, collector: RowCollector) -> None:
    """Replace the archive's rows and mark it indexed, in one transaction."""
    db.query(ArchiveChange).filter(ArchiveChange.archive_id == archive.id).delete(
        synchronize_session=False
    )
    for i in range(0, len(collector.detail), BATCH_SIZE):
        db.bulk_insert_mappings(ArchiveChange, collector.detail[i : i + BATCH_SIZE])
    summaries = collector.summary_rows()
    if summaries:
        db.bulk_insert_mappings(ArchiveChange, summaries)
    archive.history_state = "indexed"
    archive.history_indexed_at = utc_now()
    archive.history_rows = len(collector.detail) + len(summaries)
    archive.history_truncated = collector.truncated
    db.commit()


# -- executor: history_index ----------------------------------------------------


async def run_history_index(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    if not history_enabled(db):
        return Outcome(status="skipped", skip_reason="plan_locked")
    pending = (
        db.query(Archive)
        .filter(
            Archive.repository_id == repository.id, Archive.history_state == "pending"
        )
        .order_by(Archive.series.asc(), Archive.start.asc(), Archive.id.asc())
        .all()
    )
    if is_agent_executor(repository):
        for archive in pending:
            archive.history_state = "skipped"
        db.commit()
        return Outcome(
            status="skipped",
            skip_reason="agent_diff_unsupported",
            result={"archives": len(pending)},
        )
    if not pending:
        return Outcome(result={"indexed": 0, "failed": 0, "left_pending": 0})
    excludes = compile_excludes(repository.history_index_excludes)
    max_rows = settings.index_history_max_rows
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    indexed = failed = left = 0
    total = len(pending)
    try:
        for position, archive in enumerate(pending):
            if ctx.cancelled():
                break
            predecessor = predecessor_of(db, archive)
            if predecessor is not None and predecessor.history_state != "indexed":
                left += 1
                continue
            label = f"{predecessor.name if predecessor else 'full listing'} → {archive.name}"
            await ctx.progress(current=position, total=total, message=label)
            try:
                collector = await run_serialized_repository_command(
                    repository.id,
                    lambda: collect_changes(
                        ctx,
                        db,
                        repository,
                        archive,
                        predecessor,
                        env,
                        excludes,
                        max_rows,
                    ),
                    scope="metadata",
                )
                write_archive_rows(db, archive, collector)
                indexed += 1
                ctx.log(
                    f"{label}: {collector.count} changes, truncated={collector.truncated}"
                )
                # Let other coroutines (SSE, API) run between archives
                await asyncio.sleep(0)
            except OperationCancelled:
                db.rollback()
                break
            except Exception as exc:
                db.rollback()
                archive.history_state = "failed"
                db.commit()
                failed += 1
                ctx.log(f"{label}: failed: {exc}")
                logger.warning(
                    "history index failed for archive",
                    repository_id=repository.id,
                    archive=archive.name,
                    error=str(exc),
                )
        await ctx.progress(current=total, total=total, message=f"{indexed} indexed")
        status = "completed_with_warnings" if failed else "completed"
        return Outcome(
            status=status,
            result={"indexed": indexed, "failed": failed, "left_pending": left},
        )
    finally:
        cleanup_temp_key_file(temp_key_file)


# -- executor: history_merge ----------------------------------------------------


def removed_archive_ids_from_dependency(db: Session, operation) -> list[int]:
    """archive_sync reports removed archives in its result; history_merge
    always directly depends on it (spec 7.4 and 7.5 chains)."""
    depends_on_id = getattr(operation, "depends_on_id", None)
    if depends_on_id is None:
        return []
    parent = db.get(Operation, depends_on_id)
    if parent is None or parent.kind != "archive_sync":
        return []
    ids = (parent.result or {}).get("removed_archive_ids") or []
    return [int(i) for i in ids]


def _delete_rows(db: Session, archive_id: int) -> None:
    db.query(ArchiveChange).filter(ArchiveChange.archive_id == archive_id).delete(
        synchronize_session=False
    )


def merge_removed_archive(db: Session, removed: Archive) -> str:
    """Fold `removed` into its successor and delete it, in one transaction.

    Returns "folded" when both archives were indexed, "reset" when the
    successor was indexed against an archive that never was (its delta is
    now against the wrong base, so it goes back to pending), and "dropped"
    when there is no successor or the successor is not indexed yet (it will
    be diffed against the new predecessor when it is).
    """
    successor = successor_of(db, removed)
    try:
        if successor is None:
            outcome = "dropped"
        elif (
            successor.history_state == "indexed" and removed.history_state == "indexed"
        ):
            older = rows_to_changes(
                db.query(ArchiveChange)
                .filter(ArchiveChange.archive_id == removed.id)
                .all()
            )
            newer = rows_to_changes(
                db.query(ArchiveChange)
                .filter(ArchiveChange.archive_id == successor.id)
                .all()
            )
            folded = list(fold_pair(older, newer).values())
            _delete_rows(db, successor.id)
            mappings = [change_to_row_dict(c, successor.id) for c in folded]
            for i in range(0, len(mappings), BATCH_SIZE):
                db.bulk_insert_mappings(ArchiveChange, mappings[i : i + BATCH_SIZE])
            successor.history_rows = len(mappings)
            successor.history_truncated = bool(
                successor.history_truncated or removed.history_truncated
            )
            outcome = "folded"
        elif successor.history_state == "indexed":
            _delete_rows(db, successor.id)
            successor.history_state = "pending"
            successor.history_indexed_at = None
            successor.history_rows = None
            successor.history_truncated = False
            outcome = "reset"
        else:
            outcome = "dropped"
        # Explicit delete of the rows: SQLite only cascades with
        # foreign_keys=ON, which the app does not guarantee.
        _delete_rows(db, removed.id)
        db.delete(removed)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return outcome


async def run_history_merge(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    counts = {"merged": 0, "folded": 0, "reset": 0, "dropped": 0}
    ids = removed_archive_ids_from_dependency(db, ctx.operation)
    for position, archive_id in enumerate(ids):
        if ctx.cancelled():
            break
        removed = db.get(Archive, archive_id)
        if removed is None or removed.repository_id != repository.id:
            continue
        # The row is gone (and expired) after the merge commits.
        name = removed.name
        outcome = merge_removed_archive(db, removed)
        counts[outcome] += 1
        counts["merged"] += 1
        ctx.log(f"{name}: {outcome}")
        await ctx.progress(current=position + 1, total=len(ids), message=name)
        await asyncio.sleep(0)
    return Outcome(result=counts)


executors.register("history_index", run_history_index)
executors.register("history_merge", run_history_merge)
