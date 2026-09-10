"""The one-off copy of legacy job rows into `operations` (spec section 14).

Runs inside the collapse revision, on the migration's connection, before the
legacy tables are dropped. Every row becomes an `operations` row with a fresh
id and, where spec 6.2 gives the kind an extension table, a details row. The
old id is kept in `params["legacy_id"]` so a copied row can be traced back
from a log line, and the three link columns phase 8 added
(`agent_jobs.operation_id`, `script_executions.operation_id`,
`backup_plan_run_repositories.backup_operation_id`) are rewritten from the id
maps. Inline log text that the legacy tables kept on the row is written to the
operation's log file, which is where every reader looks now (spec 6.1).

Core statements rather than the ORM: the ORM no longer knows the legacy
tables, and a migration must not depend on model classes that will move on.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import MetaData, Table, delete, insert, select, update
from sqlalchemy.engine import Connection

from app.database import legacy_job_tables as legacy
from app.services.operations.package_facade import _HEADER_PREFIX
from app.services.operations.vocab import (
    LEGACY_STATUS_MAP,
    category_for,
    priority_for_trigger,
)

CHUNK = 500

# Legacy status words with no operations equivalent in LEGACY_STATUS_MAP.
_PACKAGE_STATUS = {"pending": "queued", "installing": "running"}
_WIPE_STATUS = {
    "pending": "queued",
    "completed_compaction_failed": "completed_with_warnings",
    "failed_partial": "failed",
}
_WIPE_PHASE_FOR_STATUS = {
    "completed_compaction_failed": "compact_failed",
    "failed_partial": "delete_failed_partial",
}
_RCLONE_TRIGGER = {"initial": "import", "manual": "manual", "schedule": "schedule"}
_BACKUP_MODE = {None: "server", "": "server", "local": "server"}
_LOG_MARKER = "Logs saved to: "
_PACKAGE_HEADER = _HEADER_PREFIX
_BOOL_PARAM_PREFIXES = ("scheduled_", "full_")


@dataclass
class CollapseReport:
    copied: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    id_maps: dict[str, dict[int, int]] = field(default_factory=dict)


class _Target:
    """The surviving tables, reflected from the connection so the copy sees
    exactly the schema the revision it runs in has."""

    def __init__(self, connection: Connection):
        meta = MetaData()
        meta.reflect(bind=connection)
        self.operations = meta.tables["operations"]
        self.backup_details = meta.tables["operation_backup_details"]
        self.restore_details = meta.tables["operation_restore_details"]
        self.wipe_details = meta.tables["operation_wipe_details"]
        self.rclone_details = meta.tables["operation_rclone_details"]
        self.retry_lineage = meta.tables["operation_backup_retry_lineage"]
        self.repositories = meta.tables["repositories"]
        self.agent_jobs = meta.tables["agent_jobs"]
        self.script_executions = meta.tables["script_executions"]
        self.plan_run_repositories = meta.tables["backup_plan_run_repositories"]
        self.plan_runs = meta.tables["backup_plan_runs"]
        self.scheduled_jobs = meta.tables["scheduled_jobs"]
        self.users = meta.tables["users"]
        self.ssh_connections = meta.tables["ssh_connections"]


def _status(value: Optional[str], extra: Optional[dict] = None) -> str:
    word = value or "queued"
    if extra and word in extra:
        return extra[word]
    return LEGACY_STATUS_MAP.get(word, word)


def _ids(connection: Connection, table: Table) -> set[int]:
    return set(connection.execute(select(table.c.id)).scalars().all())


def _repository_ids(
    connection: Connection, target: _Target
) -> tuple[set[int], dict[str, int]]:
    """Existing repository ids, and a path index for rows that only kept
    the path (backup and restore rows written before the id column)."""
    rows = connection.execute(
        select(target.repositories.c.id, target.repositories.c.path)
    ).all()
    ids = {row.id for row in rows}
    by_path: dict[str, int] = {}
    for row in rows:
        if row.path:
            by_path[row.path.rstrip("/") or row.path] = row.id
    return ids, by_path


def _resolve_repository(
    row, ids: set[int], by_path: dict[str, int], *, path_column: str = "repository"
) -> Optional[int]:
    repository_id = row._mapping.get("repository_id")
    if repository_id is not None and repository_id in ids:
        return repository_id
    path = row._mapping.get(path_column)
    if path:
        return by_path.get(path.rstrip("/") or path)
    return None


def _kept(value: Optional[int], known: set[int]) -> Optional[int]:
    """A foreign key the target enforces on both dialects: keep it only when
    the row it names still exists. SQLite installs can hold a dangling id."""
    return value if value is not None and value in known else None


def _insert_operation(connection: Connection, target: _Target, values: dict) -> int:
    values.setdefault("run_id", str(uuid.uuid4()))
    values.setdefault("priority", priority_for_trigger(values["trigger"]))
    values.setdefault("category", category_for(values["kind"]))
    values.setdefault("status", "queued")
    result = connection.execute(insert(target.operations).values(**values))
    return int(result.inserted_primary_key[0])


def _write_log(log_dir: Path, operation_id: int, text: str) -> str:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"operation_{operation_id}.log"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _log_path_for(
    row, log_dir: Path, operation_id: int, *, text_column: str = "logs"
) -> Optional[str]:
    """The log file a copied row points at: its own file when it had one,
    the file a `Logs saved to:` marker names when that exists, else a new
    file holding the inline text. Nothing is written for a row without logs."""
    existing = row._mapping.get("log_file_path")
    if existing:
        return existing
    text = row._mapping.get(text_column)
    if not text:
        return None
    if text.startswith(_LOG_MARKER):
        candidate = log_dir / text[len(_LOG_MARKER) :].strip()
        return str(candidate) if candidate.exists() else None
    return _write_log(log_dir, operation_id, text)


def _set_log_path(
    connection: Connection, target: _Target, operation_id: int, log_path: Optional[str]
) -> None:
    if not log_path:
        return
    connection.execute(
        update(target.operations)
        .where(target.operations.c.id == operation_id)
        .values(log_file_path=log_path)
    )


def _iter(connection: Connection, table: Table):
    """Rows in id order, in chunks, so a large table does not sit in memory."""
    last = 0
    while True:
        rows = connection.execute(
            select(table).where(table.c.id > last).order_by(table.c.id).limit(CHUNK)
        ).all()
        if not rows:
            return
        for row in rows:
            yield row
        last = rows[-1].id


def _copy_backups(connection, target, log_dir, ids, by_path, users, ssh, report):
    id_map: dict[int, int] = {}
    pending_retry: list[tuple[int, Optional[int], Optional[int]]] = []
    # `operations` enforces both of these; the legacy columns did not always
    # (`backup_jobs.scheduled_job_id` carries no ON DELETE at all), so a
    # SQLite install that ran without foreign keys can hold a dangling id
    # that would fail the whole migration on insert.
    schedules = _ids(connection, target.scheduled_jobs)
    plan_runs = _ids(connection, target.plan_runs)
    copied = 0
    for row in _iter(connection, legacy.backup_jobs):
        m = row._mapping
        repository_id = _resolve_repository(row, ids, by_path)
        if m["backup_plan_run_id"]:
            trigger = "plan"
        elif m["scheduled_job_id"]:
            trigger = "schedule"
        elif m["retry_source_job_id"]:
            trigger = "retry"
        else:
            trigger = "manual"
        params: dict[str, Any] = {"legacy_id": m["id"]}
        if repository_id is None:
            params["repository"] = m["repository"]
        mode = m["execution_mode"]
        requested_by = _kept(m["retry_requested_by_user_id"], users)
        operation_id = _insert_operation(
            connection,
            target,
            dict(
                kind="backup",
                repository_id=repository_id,
                status=_status(m["status"]),
                trigger=trigger,
                scheduled_job_id=_kept(m["scheduled_job_id"], schedules),
                backup_plan_run_id=_kept(m["backup_plan_run_id"], plan_runs),
                triggered_by_user_id=requested_by,
                execution_mode=_BACKUP_MODE.get(mode, mode),
                progress_percent=(
                    m["progress_percent"]
                    if m["progress_percent"]
                    else float(m["progress"] or 0)
                ),
                progress_message=m["current_file"],
                error_message=m["error_message"],
                params=params,
                created_at=m["created_at"],
                started_at=m["started_at"],
                completed_at=m["completed_at"],
            ),
        )
        _set_log_path(
            connection, target, operation_id, _log_path_for(row, log_dir, operation_id)
        )
        connection.execute(
            insert(target.backup_details).values(
                operation_id=operation_id,
                archive_name=m["archive_name"],
                archive_pruned_at=m["archive_pruned_at"],
                original_size=m["original_size"] or 0,
                compressed_size=m["compressed_size"] or 0,
                deduplicated_size=m["deduplicated_size"] or 0,
                nfiles=m["nfiles"] or 0,
                current_file=m["current_file"],
                backup_speed=m["backup_speed"] or 0.0,
                total_expected_size=m["total_expected_size"] or 0,
                estimated_time_remaining=m["estimated_time_remaining"] or 0,
                route_strategy=m["route_strategy"],
                source_ssh_connection_id=_kept(m["source_ssh_connection_id"], ssh),
                remote_process_pid=m["remote_process_pid"],
                remote_hostname=m["remote_hostname"],
                retry_attempt=m["retry_attempt"] or 1,
                retry_requested_by_user_id=requested_by,
                retry_requested_at=m["retry_requested_at"],
                maintenance_status=m["maintenance_status"],
            )
        )
        id_map[m["id"]] = operation_id
        if m["retry_original_job_id"] or m["retry_source_job_id"]:
            pending_retry.append(
                (operation_id, m["retry_original_job_id"], m["retry_source_job_id"])
            )
        copied += 1
    # Retry ids point at other backup rows, possibly later ones: rewrite once
    # every row has its new id.
    for operation_id, original, source in pending_retry:
        connection.execute(
            update(target.backup_details)
            .where(target.backup_details.c.operation_id == operation_id)
            .values(
                retry_original_job_id=id_map.get(original),
                retry_source_job_id=id_map.get(source),
            )
        )
    report.copied["backup_jobs"] = copied
    report.skipped["backup_jobs"] = 0
    report.id_maps["backup_jobs"] = id_map
    return id_map


def _rewrite_backup_links(connection, target, id_map, users, report):
    for table, old_col, new_col in (
        (target.agent_jobs, "backup_job_id", "operation_id"),
        (target.script_executions, "backup_job_id", "operation_id"),
        (target.plan_run_repositories, "backup_job_id", "backup_operation_id"),
    ):
        rows = connection.execute(
            select(table.c.id, table.c[old_col]).where(table.c[old_col].isnot(None))
        ).all()
        for row in rows:
            new_id = id_map.get(row[1])
            if new_id is None:
                continue
            connection.execute(
                update(table).where(table.c.id == row[0]).values({new_col: new_id})
            )
    copied = 0
    for row in _iter(connection, legacy.backup_job_retry_lineage):
        m = row._mapping
        connection.execute(
            insert(target.retry_lineage).values(
                original_job_id=id_map.get(m["original_job_id"]),
                retry_source_job_id=id_map.get(m["retry_source_job_id"]),
                attempt_number=m["attempt_number"],
                requested_by_user_id=_kept(m["requested_by_user_id"], users),
                requested_at=m["requested_at"],
                created_operation_id=id_map.get(m["created_job_id"]),
                request_snapshot=m["request_snapshot"],
            )
        )
        copied += 1
    report.copied["backup_job_retry_lineage"] = copied


def _copy_restores(connection, target, log_dir, ids, by_path, ssh, report):
    copied = 0
    for row in _iter(connection, legacy.restore_jobs):
        m = row._mapping
        repository_id = _resolve_repository(row, ids, by_path)
        operation_id = _insert_operation(
            connection,
            target,
            dict(
                kind="restore",
                repository_id=repository_id,
                status=_status(m["status"]),
                trigger="manual",
                execution_mode="server",
                progress_percent=(
                    m["progress_percent"]
                    if m["progress_percent"]
                    else float(m["progress"] or 0)
                ),
                progress_message=m["current_file"],
                error_message=m["error_message"],
                params={
                    "legacy_id": m["id"],
                    **(
                        {"repository": m["repository"]} if repository_id is None else {}
                    ),
                },
                created_at=m["created_at"],
                started_at=m["started_at"],
                completed_at=m["completed_at"],
            ),
        )
        _set_log_path(
            connection, target, operation_id, _log_path_for(row, log_dir, operation_id)
        )
        connection.execute(
            insert(target.restore_details).values(
                operation_id=operation_id,
                archive=m["archive"],
                destination=m["destination"],
                destination_type=m["destination_type"] or "local",
                destination_connection_id=_kept(m["destination_connection_id"], ssh),
                temp_extraction_path=m["temp_extraction_path"],
                destination_hostname=m["destination_hostname"],
                repository_type=m["repository_type"] or "local",
                original_size=m["original_size"] or 0,
                restored_size=m["restored_size"] or 0,
                restore_speed=m["restore_speed"] or 0.0,
                nfiles=m["nfiles"] or 0,
                current_file=m["current_file"],
            )
        )
        copied += 1
    report.copied["restore_jobs"] = copied


# (legacy table, kind, params columns, scheduled flag column). `params` keys
# are the ones `job_facade.PARAM_FIELDS` names.
_MAINTENANCE = (
    (
        legacy.check_jobs,
        "check",
        ("max_duration", "extra_flags", "scheduled_check"),
        "scheduled_check",
    ),
    (
        legacy.restore_check_jobs,
        "restore_check",
        ("archive_name", "probe_paths", "full_archive", "scheduled_restore_check"),
        "scheduled_restore_check",
    ),
    (legacy.compact_jobs, "compact", ("scheduled_compact",), "scheduled_compact"),
    (legacy.prune_jobs, "prune", ("scheduled_prune",), "scheduled_prune"),
    (legacy.delete_archive_jobs, "delete_archive", ("archive_name",), None),
)


def _copy_maintenance(connection, target, log_dir, ids, report):
    for table, kind, param_columns, flag in _MAINTENANCE:
        copied = skipped = 0
        for row in _iter(connection, table):
            m = row._mapping
            if m["repository_id"] not in ids:
                skipped += 1
                continue
            params: dict[str, Any] = {"legacy_id": m["id"]}
            for column in param_columns:
                value = m.get(column)
                if column == "probe_paths" and isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        value = [value]
                if value is not None:
                    params[column] = (
                        bool(value)
                        if column.startswith(_BOOL_PARAM_PREFIXES)
                        else value
                    )
            status = _status(m["status"])
            operation_id = _insert_operation(
                connection,
                target,
                dict(
                    kind=kind,
                    repository_id=m["repository_id"],
                    status=status,
                    skip_reason=(
                        "needs_backup" if m["status"] == "needs_backup" else None
                    ),
                    trigger="schedule" if flag and m.get(flag) else "manual",
                    execution_mode="server",
                    progress_percent=(
                        float(m["progress"]) if m.get("progress") is not None else None
                    ),
                    progress_message=m.get("progress_message"),
                    error_message=m["error_message"],
                    process_pid=m.get("process_pid"),
                    process_start_time=(
                        float(m["process_start_time"])
                        if m.get("process_start_time") is not None
                        else None
                    ),
                    params=params,
                    created_at=m["created_at"],
                    started_at=m["started_at"],
                    completed_at=m["completed_at"],
                ),
            )
            _set_log_path(
                connection,
                target,
                operation_id,
                _log_path_for(row, log_dir, operation_id),
            )
            copied += 1
        report.copied[table.name] = copied
        report.skipped[table.name] = skipped


def _copy_wipes(connection, target, log_dir, ids, users, report):
    copied = skipped = 0
    moved: list[int] = []
    for row in _iter(connection, legacy.repository_wipe_jobs):
        m = row._mapping
        if m["status"] == "previewed":
            continue
        if m["repository_id"] is not None and m["repository_id"] not in ids:
            # Not copied, so not deleted either: this is the one legacy table
            # that survives the collapse, and the row it keeps is the only
            # record left of that wipe. `moved` is the copied set.
            skipped += 1
            continue
        requested_by = _kept(m["requested_by_user_id"], users)
        confirmed_by = _kept(m["confirmed_by_user_id"], users)
        operation_id = _insert_operation(
            connection,
            target,
            dict(
                kind="wipe",
                repository_id=m["repository_id"],
                status=_status(m["status"], _WIPE_STATUS),
                trigger="manual",
                execution_mode="server",
                triggered_by_user_id=confirmed_by or requested_by,
                progress_percent=(
                    float(m["progress"]) if m["progress"] is not None else None
                ),
                progress_message=m["progress_message"],
                error_message=m["error_message"],
                params={"legacy_id": m["id"]},
                created_at=m["created_at"],
                started_at=m["started_at"],
                completed_at=m["completed_at"],
            ),
        )
        _set_log_path(
            connection, target, operation_id, _log_path_for(row, log_dir, operation_id)
        )
        connection.execute(
            insert(target.wipe_details).values(
                operation_id=operation_id,
                phase=_WIPE_PHASE_FOR_STATUS.get(m["status"], m["phase"]),
                archive_count=m["archive_count"] or 0,
                archive_fingerprint=m["archive_fingerprint"],
                archive_manifest_json=m["archive_manifest_json"],
                dry_run_output=m["dry_run_output"],
                blocking_reason=m["blocking_reason"],
                protected_archives_json=m["protected_archives_json"],
                run_compact=bool(m["run_compact"]),
                requested_by_user_id=requested_by,
                confirmed_by_user_id=confirmed_by,
                confirmed_at=m["confirmed_at"],
            )
        )
        moved.append(m["id"])
        copied += 1
    for start in range(0, len(moved), CHUNK):
        connection.execute(
            delete(legacy.repository_wipe_jobs).where(
                legacy.repository_wipe_jobs.c.id.in_(moved[start : start + CHUNK])
            )
        )
    report.copied["repository_wipe_jobs"] = copied
    report.skipped["repository_wipe_jobs"] = skipped


def _copy_rclone(connection, target, ids, report):
    copied = skipped = 0
    for row in _iter(connection, legacy.rclone_sync_jobs):
        m = row._mapping
        if m["repository_id"] not in ids:
            skipped += 1
            continue
        operation_id = _insert_operation(
            connection,
            target,
            dict(
                kind="rclone_sync",
                repository_id=m["repository_id"],
                status=_status(m["status"]),
                trigger=_RCLONE_TRIGGER.get(m["triggered_by"], "manual"),
                execution_mode="rclone",
                error_message=m["error_text"],
                log_file_path=m["log_path"],
                params={"legacy_id": m["id"]},
                created_at=m["created_at"],
                started_at=m["started_at"],
                completed_at=m["completed_at"],
            ),
        )
        connection.execute(
            insert(target.rclone_details).values(
                operation_id=operation_id,
                direction=m["direction"],
                operation=m["operation"] or "sync",
                scheduled_for=m["scheduled_for"],
                bytes_transferred=m["bytes_transferred"],
                files_transferred=m["files_transferred"],
                log_text=m["log_text"],
                error_text=m["error_text"],
            )
        )
        copied += 1
    report.copied["rclone_sync_jobs"] = copied
    report.skipped["rclone_sync_jobs"] = skipped


def _copy_packages(connection, target, log_dir, report):
    copied = 0
    for row in _iter(connection, legacy.package_install_jobs):
        m = row._mapping
        operation_id = _insert_operation(
            connection,
            target,
            dict(
                kind="package_install",
                repository_id=None,
                status=_status(m["status"], _PACKAGE_STATUS),
                trigger="manual",
                execution_mode="server",
                error_message=m["error_message"],
                result=(
                    {"exit_code": m["exit_code"]}
                    if m["exit_code"] is not None
                    else None
                ),
                process_pid=m["process_pid"],
                process_start_time=(
                    float(m["process_start_time"])
                    if m["process_start_time"] is not None
                    else None
                ),
                params={"legacy_id": m["id"], "package_id": m["package_id"]},
                created_at=m["created_at"],
                started_at=m["started_at"],
                completed_at=m["completed_at"],
            ),
        )
        stdout, stderr = m["stdout"] or "", m["stderr"] or ""
        if stdout or stderr:
            text = (
                f"{_PACKAGE_HEADER} stdout={len(stdout)} stderr={len(stderr)}\n"
                f"{stdout}{stderr}"
            )
            _set_log_path(
                connection,
                target,
                operation_id,
                _write_log(log_dir, operation_id, text),
            )
        copied += 1
    report.copied["package_install_jobs"] = copied


def collapse_legacy_job_tables(
    connection: Connection, *, log_dir: Path
) -> CollapseReport:
    """Copy every legacy job row into `operations`, in dependency order:
    backups first (the link columns and the retry lineage point at them),
    everything else after. Runs in the caller's transaction."""
    report = CollapseReport()
    target = _Target(connection)
    ids, by_path = _repository_ids(connection, target)
    users = _ids(connection, target.users)
    ssh = _ids(connection, target.ssh_connections)
    backup_map = _copy_backups(
        connection, target, log_dir, ids, by_path, users, ssh, report
    )
    _rewrite_backup_links(connection, target, backup_map, users, report)
    _copy_restores(connection, target, log_dir, ids, by_path, ssh, report)
    _copy_maintenance(connection, target, log_dir, ids, report)
    _copy_wipes(connection, target, log_dir, ids, users, report)
    _copy_rclone(connection, target, ids, report)
    _copy_packages(connection, target, log_dir, report)
    return report
