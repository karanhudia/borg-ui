"""Run the operations runner against a test's own database.

Since phase 8 the schedule and plan entry points enqueue an operation and
wait for the runner to dispatch it, instead of running the backup inline. A
test that calls one of those functions directly therefore needs a runner
bound to the session it wrote the row through.

`OperationRunner` resolves its sessions through `_session_factory` when one
is set, which is what this helper uses. Without it the runner reads the
process-wide database that `tests/conftest.py` creates empty, never sees the
queued row, and the caller's wait never ends.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

# The `SessionLocal` aliases the backup path opens its own sessions through.
# The `test_db` fixture already patches these; a test on a bare `db_session`
# does not, and the executor would otherwise run against the empty
# process-wide database and log "Job not found".
_SESSION_LOCAL_ALIASES = (
    "app.database.database.SessionLocal",
    "app.services.backup_service.SessionLocal",
    "app.services.remote_backup_service.SessionLocal",
    "app.services.operations.reconcile.SessionLocal",
    "app.api.schedule.SessionLocal",
)


@asynccontextmanager
async def operations_runner_for(session, *, patch_session_local: bool = False):
    """A live runner dispatching the operations `session` can see.

    Set `patch_session_local` for a test that does not use the `test_db`
    fixture, so the services the executor calls open their sessions on this
    database too.
    """
    from app.services.operations.executors import load_default_executors
    from app.services.operations.runner import operation_runner

    load_default_executors()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=session.get_bind())
    previous_factory = operation_runner._session_factory
    operation_runner._session_factory = factory
    patches = (
        [patch(alias, factory) for alias in _SESSION_LOCAL_ALIASES]
        if patch_session_local
        else []
    )
    for started in patches:
        started.start()
    task = asyncio.create_task(operation_runner.start())
    try:
        yield operation_runner
    finally:
        for started in patches:
            started.stop()
        operation_runner.stop()
        try:
            await asyncio.wait_for(operation_runner.drain(), timeout=30)
        except (asyncio.TimeoutError, Exception):
            pass
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        operation_runner._session_factory = previous_factory


def seed_operation(
    db,
    kind,
    *,
    repository=None,
    repository_id=None,
    status="completed",
    trigger="manual",
    params=None,
    error_message=None,
    skip_reason=None,
    log_file_path=None,
    started_at=None,
    completed_at=None,
    created_at=None,
    progress_percent=None,
    progress_message=None,
    process_pid=None,
    process_start_time=None,
    execution_mode=None,
    scheduled_job_id=None,
    backup_plan_run_id=None,
    triggered_by_user_id=None,
    run_id=None,
    depends_on_id=None,
    result=None,
    details=None,
):
    """One `operations` row in a terminal (or any) state, with its spec 6.2
    details row when the kind has one.

    Every job kind is an operation since phase 9, so a test that used to seed
    a legacy job row seeds one of these instead. `details` sets columns on the
    extension row (backup, restore, rclone sync and wipe have one).
    """
    from app.services.operations.details import (
        backup_details,
        rclone_details,
        restore_details,
        wipe_details,
    )
    from app.services.operations.enqueue import enqueue

    if repository is not None:
        if repository.id is None:
            db.flush()  # the test sessions run with autoflush off
        repository_id = repository.id

    op = enqueue(
        db,
        kind,
        repository_id=repository_id,
        trigger=trigger,
        params=params,
        execution_mode=execution_mode,
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
        triggered_by_user_id=triggered_by_user_id,
        run_id=run_id,
        depends_on_id=depends_on_id,
        commit=False,
    )
    op.status = status
    op.error_message = error_message
    op.skip_reason = skip_reason
    op.log_file_path = log_file_path
    op.started_at = started_at
    op.completed_at = completed_at
    op.progress_percent = progress_percent
    op.progress_message = progress_message
    op.process_pid = process_pid
    op.process_start_time = process_start_time
    op.result = result
    if created_at is not None:
        op.created_at = created_at
    detail_factory = {
        "backup": backup_details,
        "restore": restore_details,
        "rclone_sync": rclone_details,
        "wipe": wipe_details,
    }.get(kind)
    if details and detail_factory is None:
        raise TypeError(f"{kind} operations have no details row: {sorted(details)}")
    row = detail_factory(db, op) if detail_factory is not None else None
    for name, value in (details or {}).items():
        setattr(row, name, value)
    db.commit()
    db.refresh(op)
    return op


# Columns the legacy job tables carried that belong on the spec 6.2 extension
# row of their kind. Everything not listed here is either an `operations`
# column of the same name, translated below, or dropped because the operation
# derives it (`has_logs`, `backup_plan_id`, `repository_path`).
_DETAIL_COLUMNS = {
    "backup": (
        "archive_name",
        "archive_pruned_at",
        "original_size",
        "compressed_size",
        "deduplicated_size",
        "nfiles",
        "current_file",
        "backup_speed",
        "total_expected_size",
        "estimated_time_remaining",
        "route_strategy",
        "source_ssh_connection_id",
        "remote_process_pid",
        "remote_hostname",
        "retry_original_job_id",
        "retry_source_job_id",
        "retry_attempt",
        "retry_requested_by_user_id",
        "retry_requested_at",
        "maintenance_status",
    ),
    "restore": (
        "archive",
        "destination",
        "destination_type",
        "destination_connection_id",
        "temp_extraction_path",
        "destination_hostname",
        "repository_type",
        "original_size",
        "restored_size",
        "restore_speed",
        "nfiles",
        "current_file",
    ),
    "rclone_sync": (
        "direction",
        "operation",
        "scheduled_for",
        "bytes_transferred",
        "files_transferred",
        "log_text",
        "error_text",
    ),
    "wipe": (
        "phase",
        "archive_count",
        "archive_fingerprint",
        "archive_manifest_json",
        "dry_run_output",
        "blocking_reason",
        "protected_archives_json",
        "run_compact",
        "requested_by_user_id",
        "confirmed_by_user_id",
        "confirmed_at",
    ),
}

# Kind-specific inputs that live in `operations.params` (spec 6.2 gives the
# maintenance kinds no extension table).
_PARAM_COLUMNS = {
    "check": ("max_duration", "extra_flags", "scheduled_check"),
    "restore_check": (
        "archive_name",
        "probe_paths",
        "full_archive",
        "scheduled_restore_check",
    ),
    "compact": ("scheduled_compact",),
    "prune": ("scheduled_prune",),
    "delete_archive": ("archive_name",),
    "package_install": ("package_id",),
}

# The flag each kind used to mean "the scheduler started this".
_SCHEDULE_FLAG = {
    "check": "scheduled_check",
    "restore_check": "scheduled_restore_check",
    "compact": "scheduled_compact",
    "prune": "scheduled_prune",
}

_OPERATION_COLUMNS = (
    "started_at",
    "completed_at",
    "created_at",
    "error_message",
    "log_file_path",
    "progress_message",
    "process_pid",
    "process_start_time",
    "scheduled_job_id",
    "backup_plan_run_id",
    "triggered_by_user_id",
    "run_id",
    "depends_on_id",
    "result",
)

# Columns the operation derives rather than stores: `has_logs` from the log
# file, `backup_plan_id` through the plan run, `repository_path`,
# `repository_name` and `borg_version` from the repository, and the id from
# the insert.
_DROPPED = (
    "has_logs",
    "backup_plan_id",
    "repository_path",
    "repository_name",
    "borg_version",
    "id",
)


def seed_job_operation(db, kind, **legacy):
    """Seed the operation that replaces a legacy job row of `kind`.

    Phase 9 deleted the ten job tables, so a test that seeded one of their rows
    seeds an operation instead. This takes the column names those rows used and
    puts each value where the operation keeps it: an `operations` column, the
    kind's spec 6.2 details row, `params`, or the operation's log file. The
    status words translate too (`pending` is `queued`), so a caller keeps
    asserting the words the HTTP routes answer.
    """
    from app.database.models import Repository
    from app.services.operations.job_facade import operation_status

    repository_id = legacy.pop("repository_id", None)
    path = legacy.pop("repository", None) or legacy.get("repository_path")
    if repository_id is None and path:
        # A pending repository the caller added must be visible to the lookup:
        # the test sessions run with autoflush off.
        db.flush()
        # A legacy row could name a path with no repository row behind it; an
        # operation's repository_id is a real foreign key, so the repository a
        # caller named by path is created when the test has not made it.
        found = db.query(Repository).filter(Repository.path == path).first()
        if found is None:
            found = Repository(
                name=path.rstrip("/").rsplit("/", 1)[-1] or path,
                path=path,
                encryption="none",
                compression="lz4",
            )
            db.add(found)
            db.flush()
        repository_id = found.id
    params = dict(legacy.pop("params", None) or {})
    for column in _PARAM_COLUMNS.get(kind, ()):
        if column in legacy:
            params[column] = legacy.pop(column)
    trigger = legacy.pop("trigger", None)
    flag = _SCHEDULE_FLAG.get(kind)
    if trigger is None:
        if flag and params.get(flag):
            trigger = "schedule"
        elif kind == "backup" and legacy.get("scheduled_job_id"):
            trigger = "schedule"
        elif kind == "backup" and legacy.get("backup_plan_run_id"):
            trigger = "plan"
        elif kind == "rclone_sync":
            from app.services.operations.rclone_facade import LEGACY_TO_TRIGGER

            trigger = LEGACY_TO_TRIGGER.get(legacy.pop("triggered_by", "manual"))
        else:
            trigger = "manual"
    legacy.pop("triggered_by", None)

    status = legacy.pop("status", "completed")
    skip_reason = "needs_backup" if status == "needs_backup" else None
    details = {
        column: legacy.pop(column)
        for column in _DETAIL_COLUMNS.get(kind, ())
        if column in legacy
    }
    if kind == "rclone_sync" and "log_path" in legacy:
        legacy["log_file_path"] = legacy.pop("log_path")
    execution_mode = legacy.pop("execution_mode", None)
    if kind == "backup":
        execution_mode = {"local": "server", None: None}.get(
            execution_mode, execution_mode
        )
    elif kind == "restore":
        execution_mode = "server"
    progress = legacy.pop("progress", None)
    progress_percent = legacy.pop("progress_percent", None)
    if progress_percent is None:
        progress_percent = progress
    logs = legacy.pop("logs", None)
    stdout = legacy.pop("stdout", None)
    stderr = legacy.pop("stderr", None)
    exit_code = legacy.pop("exit_code", None)
    for column in _DROPPED:
        legacy.pop(column, None)
    fields = {name: legacy.pop(name) for name in _OPERATION_COLUMNS if name in legacy}
    if legacy:
        raise TypeError(f"unmapped legacy column(s) for {kind}: {sorted(legacy)}")
    if exit_code is not None:
        fields["result"] = {**(fields.get("result") or {}), "exit_code": exit_code}

    op = seed_operation(
        db,
        kind,
        repository_id=repository_id,
        status=operation_status(status),
        trigger=trigger,
        params=params or None,
        skip_reason=skip_reason,
        progress_percent=progress_percent,
        execution_mode=execution_mode,
        details=details,
        **fields,
    )
    if logs and not op.log_file_path:
        _write_operation_log(db, op, logs)
    if stdout is not None or stderr is not None:
        from app.services.operations.package_facade import PackageInstallFacade

        PackageInstallFacade(db, op).write_output(stdout or "", stderr or "")
        db.commit()
    db.refresh(op)
    return op


def _write_operation_log(db, op, text):
    """The inline `logs` column is the operation's log file now (spec 6.1)."""
    from app.services.operations.runner import operation_log_path

    path = operation_log_path(op.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    op.log_file_path = str(path)
    db.commit()
