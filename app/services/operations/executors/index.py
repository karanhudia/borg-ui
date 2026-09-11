"""Index executors: stats and archive_sync (spec sections 8.1 and 8.2).
Series inference follows spec 6.6 through `app.services.operations.series`.
"""

import json
import re
from typing import Iterable, Optional, Sequence

import structlog
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.repositories import (
    _agent_result_archives,
    _parse_borg_archive_time,
    _prepare_repository_borg_env,
    _repository_stats_borg_env,
    agent_timezone_for_repository,
    get_operation_timeouts,
)
from app.config import settings
from app.core.borg_router import BorgRouter
from app.database.models import Archive, Repository, SystemSettings, utc_now
from app.services.operations import executors
from app.services.operations.followups import (
    HISTORY_AVAILABLE,
    history_capability,
)
from app.services.operations.runner import Outcome, repository_busy
from app.services.operations.series import infer_series, series_prefixes_for_repository
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.repository_executor import is_agent_executor
from app.services.storage_usage import measure_repository_size, set_repository_size
from app.utils.borg_env import cleanup_temp_key_file, effective_repository_remote_path

logger = structlog.get_logger()


# -- pure helpers ---------------------------------------------------------------


def series_for(name: str, borg_version: int, prefixes: Sequence[str] = ()) -> str:
    return infer_series(name, borg_version, prefixes)


def archive_fields_from_listing(
    entry: dict,
    borg_version: int,
    *,
    timezone_name: Optional[str],
    series_prefixes: Sequence[str] = (),
) -> Optional[dict]:
    """Map one listing entry to archives columns.

    Borg renders naive wall-clock timestamps in the zone the listing ran in;
    `timezone_name` names that zone ("UTC" for server listings, the agent's
    reported zone for agent listings) so `start` and `end` are stored as
    naive UTC like every other timestamp.
    """
    borg_id = entry.get("id")
    name = entry.get("name") or entry.get("archive")
    raw_time = entry.get("start") or entry.get("time")
    if not borg_id or not name or not raw_time:
        return None
    try:
        start = _parse_borg_archive_time(raw_time, timezone_name=timezone_name)
    except ValueError:
        return None
    if start is None:
        return None
    end = None
    if entry.get("end"):
        try:
            end = _parse_borg_archive_time(entry["end"], timezone_name=timezone_name)
        except ValueError:
            end = None
    return {
        "borg_id": str(borg_id),
        "name": name,
        "series": series_for(name, borg_version, series_prefixes),
        "start": start,
        "end": end,
        "hostname": entry.get("hostname"),
        "username": entry.get("username"),
        "comment": entry.get("comment") or None,
    }


def apply_listing(
    db: Session,
    repository: Repository,
    entries: list[dict],
    *,
    timezone_name: Optional[str],
) -> tuple[list[Archive], list[int]]:
    """Upsert archives rows from a listing. Returns (new_rows, removed_ids).

    Rows missing from the listing are reported, never deleted here; the
    history_merge executor (phase 2) consumes and deletes them.
    """
    existing = {
        a.borg_id: a
        for a in db.query(Archive).filter(Archive.repository_id == repository.id).all()
    }
    seen: set[str] = set()
    new_rows: list[Archive] = []
    now = utc_now()
    prefixes = series_prefixes_for_repository(db, repository)
    for entry in entries:
        fields = archive_fields_from_listing(
            entry,
            repository.borg_version or 1,
            timezone_name=timezone_name,
            series_prefixes=prefixes,
        )
        if fields is None:
            continue
        seen.add(fields["borg_id"])
        row = existing.get(fields["borg_id"])
        if row is None:
            row = Archive(repository_id=repository.id, first_seen_at=now, **fields)
            db.add(row)
            new_rows.append(row)
        else:
            for key, value in fields.items():
                if key == "borg_id":
                    continue
                if key == "end" and value is None:
                    # listings carry no end (`borg info` does): keep the
                    # value fill_archive_info stored instead of wiping it
                    # on every sync
                    continue
                if key == "series" and value != row.series:
                    row.history_state = "pending"
                setattr(row, key, value)
        row.last_seen_at = now
    removed = [a.id for borg_id, a in existing.items() if borg_id not in seen]
    db.commit()
    for row in new_rows:
        db.refresh(row)
    return new_rows, removed


def write_repository_archive_columns(
    db: Session, repository: Repository, *, exclude_ids: Iterable[int] = ()
) -> None:
    """Derive archive_count and last_backup from the archives table (spec
    6.4). `exclude_ids` are rows reported removed that history_merge has
    not deleted yet."""
    excluded = set(exclude_ids)
    rows = [
        a
        for a in db.query(Archive).filter(Archive.repository_id == repository.id).all()
        if a.id not in excluded
    ]
    repository.archive_count = len(rows)
    repository.last_backup = max((a.start for a in rows), default=None)
    db.commit()


# -- Borg access ------------------------------------------------------------------


def _agent_listing_ok(result) -> bool:
    """True when the agent's list job actually ran borg successfully.

    A completed job can still carry a non-zero borg exit with no stdout,
    which parses to an empty list. Treating that as "no archives" wipes the
    stored count, so trust the listing (including a legitimately empty
    repository) only when nothing reports a failure. Mirrors the guard in
    `_update_agent_repository_stats`; the result shape uses either key.
    """
    if not result:
        # No result at all: the job never came back (timeout, agent gone).
        return False
    return (
        result.get("return_code", 0) == 0 and result.get("success", True) is not False
    )


async def list_archives_for_repository(
    db: Session, repository: Repository, env: dict
) -> tuple[bool, list[dict], Optional[str]]:
    """Return (ok, entries, timezone_name): whether the listing succeeded, the
    listing itself, and the zone Borg rendered its naive timestamps in.

    `ok` is False when Borg or the agent failed. Callers must not write
    derived state from a failed listing: an empty list means "borg told us
    nothing", which is indistinguishable from an empty repository.
    """
    if is_agent_executor(repository):
        from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
        from app.services.repository_executor import (
            cancel_unclaimed_agent_repository_job,
            queue_agent_repository_operation_job,
            wait_for_agent_repository_operation_job,
        )

        timeouts = get_operation_timeouts(db)
        job = queue_agent_repository_operation_job(
            db, repository, job_kind="repository.list_archives"
        )
        await dispatch_agent_job_best_effort(db, job, repository_id=repository.id)
        try:
            result = await wait_for_agent_repository_operation_job(
                db, job.id, timeout_seconds=timeouts["list_timeout"]
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
                # Left queued (the agent was not connected to take it), the
                # job is the duplicate every later list (stats, the next
                # sync) is refused for, and the reaper never reaps a queued
                # job. A list the agent claimed or runs stays: its result
                # warms the next attempt, and a dead agent's job is reaped.
                cancel_unclaimed_agent_repository_job(db, job.id)
            raise
        return (
            _agent_listing_ok(result),
            _agent_result_archives(result),
            agent_timezone_for_repository(db, repository),
        )

    router = BorgRouter(repository)
    stats_env = _repository_stats_borg_env(env)
    ok, entries = await run_serialized_repository_command(
        repository.id,
        lambda: router.list_archives_checked(env=stats_env),
        scope="metadata",
    )
    return ok, entries, "UTC"


def _info_stats(payload: str) -> Optional[dict]:
    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return None
    archives = data.get("archives") or []
    if not archives:
        return None
    entry = archives[0]
    stats = entry.get("stats") or {}
    return {
        "nfiles": stats.get("nfiles"),
        "original_size": stats.get("original_size"),
        "compressed_size": stats.get("compressed_size"),
        "deduplicated_size": stats.get("deduplicated_size"),
        "end": entry.get("end"),
        "duration": entry.get("duration"),
    }


_UTC_OFFSET_SUFFIX = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def _carries_utc_offset(value: object) -> bool:
    """True for ISO timestamps with an explicit offset (Borg 2 output)."""
    return isinstance(value, str) and _UTC_OFFSET_SUFFIX.search(value) is not None


def archive_end_resolvable(db: Session, repository: Repository) -> bool:
    """False while a naive Borg 1 time from this repository has no zone to
    be read in: an agent repository whose agent never reported one. Server
    listings run under TZ=UTC and Borg 2 renders an offset, so only that
    case is unresolvable."""
    if not is_agent_executor(repository):
        return True
    return bool(agent_timezone_for_repository(db, repository))


def archives_needing_info(
    db: Session,
    repository: Repository,
    *,
    limit: int,
    include_missing_end: bool = False,
) -> list[Archive]:
    """Archives still missing their `borg info` stats, oldest first.

    Not just the rows this run created: a repository imported with more
    archives than `INDEX_ARCHIVE_INFO_PER_RUN` fills the oldest few now and
    the rest on later runs, which is what the per-run cap is for (spec 6.4).

    `include_missing_end` also picks rows whose sizes are set but whose
    `end` is not (fill_archive_info withheld a naive end while the agent's
    zone was unknown), but only into the slots the rows without sizes leave
    free: a row whose end can never be parsed costs at most a spare slot per
    run and never displaces an archive that has no stats at all.
    """
    if limit <= 0:
        return []

    def _select(predicate, exclude_ids: set[int], n: int) -> list[Archive]:
        q = db.query(Archive).filter(Archive.repository_id == repository.id, predicate)
        if exclude_ids:
            q = q.filter(Archive.id.notin_(exclude_ids))
        return q.order_by(Archive.start.asc()).limit(n).all()

    rows = _select(Archive.original_size.is_(None), set(), limit)
    spare = limit - len(rows)
    if include_missing_end and spare > 0:
        rows += _select(Archive.end.is_(None), {a.id for a in rows}, spare)
    return rows


class AgentUnavailable(RuntimeError):
    """The agent did not answer a per-archive job within the timeout."""


async def _agent_archive_info(
    db: Session, repository: Repository, archive: Archive, *, timeout_seconds: int
) -> Optional[dict]:
    """Run `repository.archive_info` on the agent for one archive.

    Borg 2 archives are addressed by `aid:<id>` so a series name never
    resolves to a different archive; Borg 1 has no id selector.
    """
    from app.services.agent_job_dispatcher import (
        dispatch_agent_cancel_if_connected,
        dispatch_agent_job_best_effort,
    )
    from app.services.repository_executor import (
        abandon_agent_repository_operation_job,
        queue_agent_repository_operation_job,
        wait_for_agent_repository_operation_job,
    )

    ref = (
        f"aid:{archive.borg_id}"
        if (repository.borg_version or 1) == 2
        else archive.name
    )
    job = queue_agent_repository_operation_job(
        db, repository, job_kind="repository.archive_info", operation={"archive": ref}
    )
    await dispatch_agent_job_best_effort(
        db, job, repository_id=repository.id, archive_name=ref
    )
    try:
        result = await wait_for_agent_repository_operation_job(
            db, job.id, timeout_seconds=timeout_seconds
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_504_GATEWAY_TIMEOUT:
            raise
        # Left behind, the job counts as active repository work for every
        # later archive_info and stats request (the reaper never reaps a
        # queued job). Cancel it, and tell the caller the agent is gone.
        abandoned = abandon_agent_repository_operation_job(db, job.id)
        if abandoned is not None and abandoned.status == "cancel_requested":
            await dispatch_agent_cancel_if_connected(abandoned)
        raise AgentUnavailable(
            f"no answer from the agent within {timeout_seconds}s"
        ) from exc
    if not _agent_listing_ok(result):
        return None
    return {"success": True, "stdout": result.get("stdout") or ""}


async def _server_archive_info(
    repository: Repository, archive: Archive, env: dict
) -> Optional[dict]:
    remote_path = effective_repository_remote_path(repository)
    # TZ=UTC so borg renders the archive end time in UTC (see stats env).
    info_env = _repository_stats_borg_env(env or {})
    if (repository.borg_version or 1) == 2:
        from app.core.borg2 import borg2

        return await run_serialized_repository_command(
            repository.id,
            lambda: borg2.info_archive(
                repository.path,
                f"aid:{archive.borg_id}",
                passphrase=repository.passphrase,
                remote_path=remote_path,
                bypass_lock=repository.bypass_lock,
                env=info_env,
            ),
            scope="metadata",
        )
    from app.core.borg import borg

    return await run_serialized_repository_command(
        repository.id,
        lambda: borg.info_archive(
            repository.path,
            archive.name,
            passphrase=repository.passphrase,
            remote_path=remote_path,
            bypass_lock=repository.bypass_lock,
            env=info_env,
        ),
        scope="metadata",
    )


async def fill_archive_info(
    db: Session,
    repository: Repository,
    archives: list[Archive],
    env: dict,
    *,
    limit: int,
) -> int:
    """Run per-archive `borg info` for up to `limit` archives, oldest first.

    Agent repositories go through the agent's `repository.archive_info` job;
    the agent renders naive Borg 1 timestamps in its reported zone.
    """
    if limit <= 0:
        return 0
    agent = is_agent_executor(repository)
    timezone_name = agent_timezone_for_repository(db, repository) if agent else "UTC"
    timeout_seconds = get_operation_timeouts(db)["info_timeout"] if agent else None
    filled = 0
    for archive in sorted(archives, key=lambda a: a.start)[:limit]:
        try:
            if agent:
                result = await _agent_archive_info(
                    db, repository, archive, timeout_seconds=timeout_seconds
                )
            else:
                result = await _server_archive_info(repository, archive, env)
        except AgentUnavailable as exc:
            # every further archive would wait out the same timeout
            logger.warning(
                "archive info abandoned, agent not answering",
                archive=archive.name,
                error=str(exc),
            )
            break
        except Exception as exc:
            if repository_busy(exc):
                # another job took the repository between two archives: the
                # runner defers the whole operation and retries later, which
                # beats one refused job per remaining archive
                raise
            logger.warning("archive info failed", archive=archive.name, error=str(exc))
            continue
        if not result or not result.get("success"):
            continue
        info = _info_stats(result.get("stdout", ""))
        if info is None:
            continue
        archive.nfiles = info["nfiles"]
        archive.original_size = info["original_size"]
        archive.compressed_size = info["compressed_size"]
        archive.deduplicated_size = info["deduplicated_size"]
        if info["end"] and (timezone_name or _carries_utc_offset(info["end"])):
            # A naive end time from an agent that never reported its zone
            # would be read in the server's zone; leave it unset instead.
            try:
                archive.end = _parse_borg_archive_time(
                    info["end"], timezone_name=timezone_name
                )
            except ValueError:
                pass
        if info["duration"] is not None:
            archive.duration_seconds = float(info["duration"])
        filled += 1
    db.commit()
    return filled


# -- executors -------------------------------------------------------------------


def _publish_mqtt_state(db: Session, reason: str) -> None:
    """Best-effort Home Assistant state publish after repository columns change.

    The retired stats refresh loop did this once per cycle; the executors that
    now write archive_count, last_backup, and total_size keep the behaviour.
    """
    try:
        from app.services.mqtt_service import mqtt_service

        mqtt_service.sync_state_with_db(db, reason=reason)
    except Exception as exc:
        logger.warning("MQTT state publish failed", reason=reason, error=str(exc))


def _load_repository(ctx) -> Optional[Repository]:
    if ctx.repository_id is None:
        return None
    return ctx.db.get(Repository, ctx.repository_id)


async def run_stats(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    if is_agent_executor(repository):
        # The agent measures its own repository (repo-info for Borg 1,
        # disk_usage for Borg 2) and also refreshes encryption. The retired
        # stats refresh loop called this for every repository; without it
        # agent repositories would never refresh size in the background.
        from app.api.repositories import _update_agent_repository_stats

        # The admission's refusal (another job of this repository is active)
        # must reach the runner: it defers the operation and retries, as it
        # does for archive_sync, instead of recording a failure for a race
        # the follow-up chains of one backup lose against each other.
        updated = await _update_agent_repository_stats(repository, db, raise_busy=True)
        if not updated:
            return Outcome(
                status="failed", error_message="agent repository stats refresh failed"
            )
        _publish_mqtt_state(db, "operations stats")
        ctx.log(f"agent repository size {repository.total_size}")
        return Outcome(
            result={"total_size": repository.total_size, "executor": "agent"}
        )
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        system_settings = db.query(SystemSettings).first()
        use_bypass_lock = bool(
            repository.bypass_lock
            or (system_settings and system_settings.bypass_lock_on_list)
        )
        timeouts = get_operation_timeouts(db)
        measured = await run_serialized_repository_command(
            repository.id,
            lambda: measure_repository_size(
                repository,
                env=env,
                temp_key_file=temp_key_file,
                info_timeout=timeouts["info_timeout"],
                use_bypass_lock=use_bypass_lock,
            ),
            scope="metadata",
        )
        # `measure_repository_size` reports unknown as None and never 0, so
        # this is "a size came back"; an emptied repository reads as unknown
        # and keeps its stored size until a source can say "empty"
        if measured.bytes:
            set_repository_size(repository, measured.bytes, measured.source)
        if measured.last_modified:
            repository.borg_last_modified = measured.last_modified
        if system_settings is not None:
            system_settings.last_stats_refresh = utc_now()
        db.commit()
        if measured.bytes:
            _publish_mqtt_state(db, "operations stats")
        ctx.log(
            f"repository size {measured.bytes} bytes ({measured.source or 'unknown'})"
        )
        return Outcome(
            result={
                "bytes": measured.bytes,
                "objects": measured.objects,
                "source": measured.source,
                "last_modified": measured.last_modified.isoformat()
                if measured.last_modified
                else None,
            }
        )
    finally:
        cleanup_temp_key_file(temp_key_file)


async def run_archive_sync(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    if (repository.borg_version or 1) != 2 and not archive_end_resolvable(
        db, repository
    ):
        # A Borg 1 listing is naive wall clock in the zone the agent ran it
        # in. Without that zone the times would be stored in the server's
        # zone, and `start` is NOT NULL, so there is no row to withhold it
        # from. The agent reports its zone on hello; the next reconcile
        # retries.
        return Outcome(
            status="failed",
            error_message=(
                "agent has not reported its timezone; Borg 1 archive times "
                "cannot be placed until it does"
            ),
        )
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        ok, entries, timezone_name = await list_archives_for_repository(
            db, repository, env
        )
        if not ok:
            # An empty list from a failed borg call is not an empty
            # repository. Writing it would zero archive_count, clear
            # last_backup, and report every archive as removed - which
            # history_merge would then act on.
            return Outcome(status="failed", error_message="listing archives failed")
        new_rows, removed_ids = apply_listing(
            db, repository, entries, timezone_name=timezone_name
        )
        if is_agent_executor(repository):
            # No history run ever reaches an agent's repository (the server
            # cannot diff it), so the listing records the state the history
            # run used to write: `skipped`, not a `pending` that would read
            # as "not yet". On every plan: the capability is the executor's
            # and outlasts a plan change. `failed` is marked too: nothing can retry it
            # here, and a row left `failed` would flag the repository and
            # offer a rebuild that is refused. Moving the repository back to
            # the server reopens every `skipped` archive with a fresh retry
            # budget.
            db.query(Archive).filter(
                Archive.repository_id == repository.id,
                Archive.history_state.in_(("pending", "failed")),
            ).update({Archive.history_state: "skipped"}, synchronize_session=False)
            db.commit()
        elif (
            db.query(Archive.id)
            .filter(
                Archive.repository_id == repository.id,
                Archive.history_state == "skipped",
            )
            .first()
            is not None
            and history_capability(db, repository) == HISTORY_AVAILABLE
        ):
            # The mirror image: `skipped` on a server's repository is left
            # over from an agent-executed past (the executor change reopens
            # them, but rows written before it did so stay). With the history
            # stage available they go back to `pending` with a fresh budget,
            # and the chain's history stage picks them up. The plan lookup
            # behind the capability commits, so it runs only with such rows.
            db.query(Archive).filter(
                Archive.repository_id == repository.id,
                Archive.history_state == "skipped",
            ).update(
                {Archive.history_state: "pending", Archive.history_attempts: 0},
                synchronize_session=False,
            )
            db.commit()
        filled = await fill_archive_info(
            db,
            repository,
            archives_needing_info(
                db,
                repository,
                limit=settings.index_archive_info_per_run,
                include_missing_end=True,
            ),
            env,
            limit=settings.index_archive_info_per_run,
        )
        write_repository_archive_columns(db, repository, exclude_ids=removed_ids)
        _publish_mqtt_state(db, "operations archive sync")
        ctx.log(
            f"listed {len(entries)} archives, {len(new_rows)} new, {filled} info fetched"
        )
        await ctx.progress(
            current=len(entries),
            total=len(entries),
            message=f"{len(entries)} archives",
        )
        return Outcome(
            result={
                "listed": len(entries),
                "new": len(new_rows),
                "info_filled": filled,
                "removed_archive_ids": removed_ids,
            }
        )
    finally:
        cleanup_temp_key_file(temp_key_file)


executors.register("stats", run_stats)
executors.register("archive_sync", run_archive_sync)
