"""Index executors: stats and archive_sync (spec sections 8.1 and 8.2).

Series inference here is the phase 1 placeholder: Borg 2 uses the archive
name (Borg 2 defines series that way); Borg 1 uses "default". Phase 2
replaces `series_for` with the full inference of spec section 6.6.
"""

import json
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.api.repositories import (
    _agent_result_archives,
    _parse_borg_archive_time,
    _prepare_repository_borg_env,
    _repository_stats_borg_env,
    format_bytes,
    get_operation_timeouts,
)
from app.config import settings
from app.core.borg_router import BorgRouter
from app.database.models import Archive, Repository, SystemSettings, utc_now
from app.services.operations import executors
from app.services.operations.runner import Outcome
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.repository_executor import is_agent_executor
from app.utils.borg_env import cleanup_temp_key_file, effective_repository_remote_path

logger = structlog.get_logger()


# -- pure helpers ---------------------------------------------------------------


def series_for(name: str, borg_version: int) -> str:
    return name if borg_version == 2 else "default"


def archive_fields_from_listing(entry: dict, borg_version: int) -> Optional[dict]:
    borg_id = entry.get("id")
    name = entry.get("name") or entry.get("archive")
    raw_time = entry.get("start") or entry.get("time")
    if not borg_id or not name or not raw_time:
        return None
    try:
        start = _parse_borg_archive_time(raw_time)
    except ValueError:
        return None
    if start is None:
        return None
    end = None
    if entry.get("end"):
        try:
            end = _parse_borg_archive_time(entry["end"])
        except ValueError:
            end = None
    return {
        "borg_id": str(borg_id),
        "name": name,
        "series": series_for(name, borg_version),
        "start": start,
        "end": end,
        "hostname": entry.get("hostname"),
        "username": entry.get("username"),
        "comment": entry.get("comment") or None,
    }


def apply_listing(
    db: Session, repository: Repository, entries: list[dict]
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
    for entry in entries:
        fields = archive_fields_from_listing(entry, repository.borg_version or 1)
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
                if key == "series" and value != row.series:
                    row.history_state = "pending"
                setattr(row, key, value)
        row.last_seen_at = now
    removed = [a.id for borg_id, a in existing.items() if borg_id not in seen]
    db.commit()
    for row in new_rows:
        db.refresh(row)
    return new_rows, removed


# -- Borg access ------------------------------------------------------------------


async def list_archives_for_repository(
    db: Session, repository: Repository, env: dict
) -> list[dict]:
    if is_agent_executor(repository):
        from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
        from app.services.repository_executor import (
            queue_agent_repository_operation_job,
            wait_for_agent_repository_operation_job,
        )

        timeouts = get_operation_timeouts(db)
        job = queue_agent_repository_operation_job(
            db, repository, job_kind="repository.list_archives"
        )
        await dispatch_agent_job_best_effort(db, job, repository_id=repository.id)
        result = await wait_for_agent_repository_operation_job(
            db, job.id, timeout_seconds=timeouts["list_timeout"]
        )
        return _agent_result_archives(result)

    router = BorgRouter(repository)
    stats_env = _repository_stats_borg_env(env)
    return await run_serialized_repository_command(
        repository.id, lambda: router.list_archives(env=stats_env), scope="metadata"
    )


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


async def fill_archive_info(
    db: Session,
    repository: Repository,
    archives: list[Archive],
    env: dict,
    *,
    limit: int,
) -> int:
    """Run per-archive `borg info` for up to `limit` archives, oldest first."""
    if is_agent_executor(repository) or limit <= 0:
        return 0
    filled = 0
    remote_path = effective_repository_remote_path(repository)
    for archive in sorted(archives, key=lambda a: a.start)[:limit]:
        try:
            if (repository.borg_version or 1) == 2:
                from app.core.borg2 import borg2

                result = await borg2.info_archive(
                    repository.path,
                    f"aid:{archive.borg_id}",
                    passphrase=repository.passphrase,
                    remote_path=remote_path,
                    bypass_lock=repository.bypass_lock,
                    env=env or None,
                )
            else:
                from app.core.borg import borg

                result = await borg.info_archive(
                    repository.path,
                    archive.name,
                    passphrase=repository.passphrase,
                    remote_path=remote_path,
                    bypass_lock=repository.bypass_lock,
                    env=env or None,
                )
        except Exception as exc:
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
        if info["end"]:
            try:
                archive.end = _parse_borg_archive_time(info["end"])
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
    if is_agent_executor(repository):
        return Outcome(
            result={"unique_csize": None, "reason": "agent_size_unsupported"}
        )
    db = ctx.db
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        system_settings = db.query(SystemSettings).first()
        use_bypass_lock = bool(
            repository.bypass_lock
            or (system_settings and system_settings.bypass_lock_on_list)
        )
        timeouts = get_operation_timeouts(db)
        router = BorgRouter(repository)
        total = await run_serialized_repository_command(
            repository.id,
            lambda: router.calculate_total_size_bytes(
                env=env,
                info_timeout=timeouts["info_timeout"],
                use_bypass_lock=use_bypass_lock,
                temp_key_file=temp_key_file,
            ),
            scope="metadata",
        )
        if total and total > 0:
            repository.total_size = format_bytes(total)
            db.commit()
            _publish_mqtt_state(db, "operations stats")
        ctx.log(f"repository size {total} bytes")
        return Outcome(result={"unique_csize": total})
    finally:
        cleanup_temp_key_file(temp_key_file)


async def run_archive_sync(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        entries = await list_archives_for_repository(db, repository, env)
        new_rows, removed_ids = apply_listing(db, repository, entries)
        filled = await fill_archive_info(
            db, repository, new_rows, env, limit=settings.index_archive_info_per_run
        )
        rows = db.query(Archive).filter(Archive.repository_id == repository.id).all()
        repository.archive_count = len(rows)
        if rows:
            repository.last_backup = max(a.start for a in rows)
        db.commit()
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
