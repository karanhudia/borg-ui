"""
Activity feed API endpoints.

Provides a unified view of all operations (backups, restores, checks, compacts, package installs).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Any, List, Optional
from datetime import datetime
from pydantic import BaseModel
import os
import structlog
import tempfile

from app.database.database import get_db
from app.database.models import (
    AgentJob,
    AgentJobLog,
    BackupPlan,
    BackupPlanRun,
    AvailabilityScheduleSkip,
    Repository,
    InstalledPackage,
    Operation,
    ScheduledJob,
    ScriptExecution,
)
from app.api.auth import get_current_user, User
from app.core.security import check_repo_access, get_current_download_user
from app.utils.datetime_utils import serialize_datetime
from app.services.backup_service import backup_service
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations import vocab as op_vocab
from app.services.operations.models import serialize_operation

logger = structlog.get_logger()

router = APIRouter(prefix="/api/activity", tags=["activity"])


def _get_agent_job_for_backup(db: Session, operation_id: int) -> Optional[AgentJob]:
    return (
        db.query(AgentJob)
        .filter(AgentJob.operation_id == operation_id)
        .order_by(AgentJob.id.desc())
        .first()
    )


def _get_agent_log_lines(db: Session, agent_job_id: int) -> list[str]:
    logs = (
        db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == agent_job_id)
        .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
        .all()
    )
    return [log.message for log in logs]


class ActivityItem(BaseModel):
    activity_key: Optional[str] = None
    id: int
    type: str  # backup, restore, check, restore_check, compact, package, rclone_*
    status: str  # 'pending', 'running', 'completed', 'needs_backup', 'failed', 'completed_with_warnings'
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    repository: Optional[str]  # Repository path/name (if applicable)
    log_file_path: Optional[str]  # Path to streaming log file
    triggered_by: str = "manual"  # 'manual' or 'schedule'
    schedule_id: Optional[int] = None  # ScheduledJob ID if triggered_by schedule
    schedule_name: Optional[str] = None  # Schedule name if triggered_by schedule
    backup_plan_id: Optional[int] = None  # BackupPlan ID if triggered by a plan
    backup_plan_run_id: Optional[int] = None  # BackupPlanRun ID if triggered by a plan
    backup_plan_name: Optional[str] = None  # BackupPlan name if triggered by a plan
    skip_reason: Optional[str] = None

    # Type-specific metadata
    archive_name: Optional[str] = None  # For backup/restore
    archive_pruned_at: Optional[datetime] = None  # backup: its archive is gone
    package_name: Optional[str] = None  # For package installs
    has_logs: bool = False  # Whether logs are available for download
    repository_path: Optional[str] = (
        None  # Full repository path (for mapping to friendly name)
    )

    # Operations fields (spec 9.1). Optional so legacy rows validate unchanged.
    kind: Optional[str] = None
    category: Optional[str] = None
    trigger: Optional[str] = None
    priority: Optional[int] = None
    run_id: Optional[str] = None
    depends_on_id: Optional[int] = None
    repository_id: Optional[int] = None
    progress_percent: Optional[float] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    progress_message: Optional[str] = None
    execution_mode: Optional[str] = None
    created_at: Optional[datetime] = None
    # Script executions only: the hook that ran the script and the operation
    # it ran around. With collapse_runs a hook rides under that operation.
    operation_id: Optional[int] = None
    hook_type: Optional[str] = None
    # The key the feed is sorted by. Pass the last item's value back as
    # `before` to page into older history.
    sort_at: Optional[datetime] = None
    followups: List["ActivityItem"] = []

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


ActivityItem.model_rebuild()


def _paginate_log_text(log_text: str, offset: int, limit: int) -> dict:
    lines = log_text.split("\n") if log_text else []
    total_lines = len(lines)
    end_offset = min(offset + limit, total_lines)
    chunk = lines[offset:end_offset]
    return {
        "lines": [
            {"line_number": offset + i + 1, "content": line}
            for i, line in enumerate(chunk)
        ],
        "total_lines": total_lines,
        "has_more": end_offset < total_lines,
    }


# Activity type names that are not operation kind names. `package` predates
# the operations vocabulary; the two rclone names share one kind (spec 6.2).
_ACTIVITY_TYPE_TO_KIND = {"package": "package_install"}
_KIND_TO_ACTIVITY_TYPE = {"package_install": "package"}


def operation_kind_for_activity_type(job_type: str) -> str:
    return _ACTIVITY_TYPE_TO_KIND.get(job_type, job_type)


def _is_operation_only_kind(job_type: str, job_models: dict) -> bool:
    """True for the kinds the generic operation branch can serve, which since
    phase 9 is every kind except script executions and the two mirror names.

    A mirror keeps its own branch below: its log text lives in two columns of
    the spec 6.2 details row (`log_text` and `error_text`), not in the
    operation's log file, and its routes answer a placeholder line while the
    sync is queued."""
    return (
        job_type not in job_models
        and job_type not in RCLONE_ACTIVITY_OPERATIONS
        and operation_kind_for_activity_type(job_type) in op_vocab.KINDS
    )


def _running_backup_log_response(job_id: int, offset: int, limit: int) -> dict:
    """The live view of a backup that is still running: the service's
    in-memory tail, or a waiting message while it has produced nothing yet."""
    log_buffer, buffer_exists = backup_service.get_log_buffer(job_id, tail_lines=500)
    logger.info(
        "Retrieved log buffer for running backup",
        job_id=job_id,
        buffer_exists=buffer_exists,
        buffer_length=len(log_buffer),
        buffer_type=type(log_buffer).__name__,
    )
    if buffer_exists and len(log_buffer) > 0:
        return {
            "lines": [
                {"line_number": i + 1, "content": line}
                for i, line in enumerate(log_buffer)
            ],
            "total_lines": len(log_buffer),
            # Always show the tail for a running job.
            "has_more": False,
        }
    if offset > 0:
        return {"lines": [], "total_lines": 0, "has_more": False}
    if buffer_exists:
        # The borg command started and has not written its first line yet.
        lines = [
            "Backup is running...",
            "",
            "Processing started, waiting for first log output...",
            "",
            "Note: Showing last 500 lines from in-memory buffer. Full logs not saved to disk.",
        ]
    else:
        lines = [
            "Backup is currently running...",
            "",
            "Waiting for logs...",
            "",
            "Note: Showing last 500 lines from in-memory buffer. Full logs not saved to disk.",
        ]
    return {
        "lines": [
            {"line_number": i + 1, "content": line} for i, line in enumerate(lines)
        ],
        "total_lines": len(lines),
        "has_more": False,
    }


def _operation_log_sources(db: Session, job_type: str, op) -> dict:
    """How an operation-only kind's logs are read and policy-gated.

    `package` keeps the two-stream shape its route contract promises: the
    facade parses them back out of the operation's log file (spec 6.2 gives
    the kind no extension table).
    """
    if job_type == "package":
        from app.services.operations.package_facade import PackageInstallFacade

        job = PackageInstallFacade(db, op)
        return {
            "output_text": [job.stdout, job.stderr, job.error_message],
            "file_path": getattr(job, "log_file_path", None),
            "exit_code": job.exit_code,
            "text": _format_package_install_logs(job),
        }
    if job_type == "backup":
        from app.services.operations.backup_facade import (
            BackupJobFacade,
            backup_job_has_logs,
        )
        from app.services.repository_executor import get_agent_job_for_backup

        job = BackupJobFacade(db, op)
        text = _read_operation_log(op)
        if job.execution_mode == "agent":
            agent_job = get_agent_job_for_backup(db, job)
            if agent_job is not None:
                text = "\n".join(_get_agent_log_lines(db, agent_job.id)) or text
        return {
            "output_text": [job.logs, job.error_message],
            "file_path": getattr(op, "log_file_path", None),
            "exit_code": None,
            "text": text,
            "has_logs": backup_job_has_logs(db, job),
        }
    return {
        "output_text": [op.error_message],
        "file_path": op.log_file_path,
        "exit_code": None,
        "text": _read_operation_log(op),
    }


def _get_operation_or_404(
    db: Session, job_type: str, job_id: int, current_user: Optional[User] = None
) -> Operation:
    kind = operation_kind_for_activity_type(job_type)
    op = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == kind)
        .first()
    )
    if not op:
        raise HTTPException(
            status_code=404,
            detail={
                "key": "backend.errors.activity.jobNotFound",
                "params": {"jobType": job_type},
            },
        )
    # A package install carries no repository, so the check is conditional.
    if current_user is not None and op.repository_id is not None:
        repo = db.get(Repository, op.repository_id)
        if repo is not None:
            check_repo_access(db, current_user, repo, "viewer")
    return op


def _read_operation_log(op: Operation) -> str:
    log_file_path = op.log_file_path
    if not log_file_path:
        return ""
    try:
        with open(log_file_path, "r", encoding="utf-8", errors="replace") as fh:
            # A trailing newline terminates the last line rather than starting
            # an empty one, so the line count matches what a file reader sees.
            return fh.read().rstrip("\n")
    except OSError:
        return ""


def _script_execution_display_name(execution: ScriptExecution) -> str:
    """Human label for a script execution: the library script name, or the
    agent-published script name for agent hooks (which have no ``script_id``)."""
    if execution.script:
        return execution.script.name
    if execution.agent_script_name:
        return execution.agent_script_name
    return f"Script #{execution.script_id}"


def _format_script_execution_logs(execution: ScriptExecution) -> str:
    script_name = _script_execution_display_name(execution)
    lines = [
        f"SCRIPT: {script_name}",
        f"HOOK: {execution.hook_type or 'standalone'}",
        f"STATUS: {execution.status}",
    ]
    if execution.exit_code is not None:
        lines.append(f"EXIT CODE: {execution.exit_code}")
    if execution.execution_time is not None:
        lines.append(f"EXECUTION TIME: {execution.execution_time:.2f}s")
    lines.extend(
        [
            "",
            "STDOUT:",
            execution.stdout or "(empty)",
            "",
            "STDERR:",
            execution.stderr or "(empty)",
        ]
    )
    if execution.error_message:
        lines.extend(["", "ERROR:", execution.error_message])
    return "\n".join(lines)


# Cap the live-log tail read on the 2s polling path so a verbose hook (e.g. a
# large line-by-line DB dump) can't grow the query + string rebuild unbounded.
_MAX_LIVE_LOG_ROWS = 500


def _format_running_agent_script_logs(execution: ScriptExecution, db: Session) -> str:
    """Live log for a still-running agent hook: the header plus the agent's
    streamed ``agent_job_logs`` lines, which arrive before the terminal
    stdout/stderr are captured at completion. The frontend polls this every 2s
    while the execution is ``running`` (same as a live borg job), so only the
    last ``_MAX_LIVE_LOG_ROWS`` rows are read (the most recent activity)."""
    # Only ``message``/``stream`` are used below, and this runs on a 2s-polling
    # hot path — project just those two columns instead of hydrating full ORM
    # rows (mirrors ``_latest_agent_script_line`` in ``app/api/backup_plans.py``).
    rows = (
        db.query(AgentJobLog.message, AgentJobLog.stream)
        .filter(AgentJobLog.agent_job_id == execution.agent_job_id)
        .order_by(AgentJobLog.sequence.desc(), AgentJobLog.id.desc())
        .limit(_MAX_LIVE_LOG_ROWS)
        .all()
    )
    rows.reverse()  # back to chronological order after the tail fetch
    stdout_lines = [row.message for row in rows if row.stream != "stderr"]
    stderr_lines = [row.message for row in rows if row.stream == "stderr"]
    lines = [
        f"SCRIPT: {_script_execution_display_name(execution)}",
        f"HOOK: {execution.hook_type or 'standalone'}",
        f"STATUS: {execution.status}",
        "",
        "STDOUT:",
        "\n".join(stdout_lines) if stdout_lines else "(no output yet)",
        "",
        "STDERR:",
        "\n".join(stderr_lines) if stderr_lines else "(no output yet)",
    ]
    return "\n".join(lines)


RCLONE_ACTIVITY_OPERATIONS = {
    "rclone_sync": "sync",
    "rclone_hydrate": "hydrate",
}


def _no_logs_available_exception() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"key": "backend.errors.activity.noLogsAvailableForJob"},
    )


def _format_rclone_job_logs(job) -> str:
    parts = []
    if job.log_text:
        parts.append(job.log_text)
    if job.error_text and job.error_text not in (job.log_text or ""):
        parts.append(job.error_text)
    return "\n".join(parts)


def _format_package_install_logs(job) -> str:
    lines = [f"PACKAGE: Package #{job.package_id}", f"STATUS: {job.status}"]
    if job.exit_code is not None:
        lines.append(f"EXIT CODE: {job.exit_code}")
    lines.extend(
        [
            "",
            "STDOUT:",
            job.stdout or "(empty)",
            "",
            "STDERR:",
            job.stderr or "(empty)",
        ]
    )
    if job.error_message:
        lines.extend(["", "ERROR:", job.error_message])
    return "\n".join(lines)


def _get_rclone_job(db: Session, job_type: str, job_id: int):
    """Operations first, then a pre-phase-6 legacy row (spec 6.2)."""
    from app.services.operations.rclone_facade import resolve_rclone_job

    return resolve_rclone_job(
        db, job_id, operation=RCLONE_ACTIVITY_OPERATIONS[job_type]
    )


def _activity_log_policy_sources(job_type: str, job: Any) -> dict[str, Any]:
    if job_type == "script_execution":
        return {
            "output_text": [
                getattr(job, "stdout", None),
                getattr(job, "stderr", None),
                getattr(job, "error_message", None),
            ],
            "file_path": None,
            "exit_code": getattr(job, "exit_code", None),
        }
    if job_type in RCLONE_ACTIVITY_OPERATIONS:
        return {
            "output_text": [
                getattr(job, "log_text", None),
                getattr(job, "error_text", None),
            ],
            "file_path": getattr(job, "log_path", None),
            "exit_code": None,
        }
    if job_type == "package":
        return {
            "output_text": [
                getattr(job, "stdout", None),
                getattr(job, "stderr", None),
                getattr(job, "error_message", None),
            ],
            "file_path": getattr(job, "log_file_path", None),
            "exit_code": getattr(job, "exit_code", None),
        }
    return {
        "output_text": [
            getattr(job, "logs", None),
            getattr(job, "error_message", None),
        ],
        "file_path": getattr(job, "log_file_path", None),
        "exit_code": getattr(job, "exit_code", None),
    }


def _activity_job_has_logs(job_type: str, job: Any, *, log_save_policy: str) -> bool:
    sources = _activity_log_policy_sources(job_type, job)
    return job_has_logs_by_policy(
        job,
        log_save_policy,
        output_text=sources["output_text"],
        file_path=sources["file_path"],
        exit_code=sources["exit_code"],
    )


def _ensure_activity_logs_visible(job_type: str, job: Any, db: Session) -> None:
    if not _activity_job_has_logs(
        job_type, job, log_save_policy=get_log_save_policy(db)
    ):
        raise _no_logs_available_exception()


def _text_download_response(log_text: str, *, filename: str) -> FileResponse:
    temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    try:
        temp_file.write(log_text)
        temp_file.flush()
        temp_file.close()
        return FileResponse(
            path=temp_file.name,
            filename=filename,
            media_type="text/plain",
            background=BackgroundTask(os.unlink, temp_file.name),
        )
    except Exception as e:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        raise e


def _category_for_non_operation_type(item_type: str) -> str:
    """The category of an Activity item that is not an operation: a script
    execution or an availability skip."""
    if item_type in op_vocab.KINDS:
        return op_vocab.category_for(item_type)
    return "system"


def _trigger_for_non_operation_item(item: dict) -> str:
    if item.get("backup_plan_run_id"):
        return "plan"
    return "schedule" if item.get("triggered_by") == "schedule" else "manual"


def _apply_legacy_activity_shape(
    db: Session, op: Operation, item: dict, *, log_save_policy: str
) -> None:
    """Give a migrated operation the Activity vocabulary its legacy table used.

    Activity's `type` is not always the operation kind: one `rclone_sync` kind
    serves two activity names (spec 6.2 puts the sub-type on the details row),
    and its `triggered_by` keeps the legacy word `initial` the frontend reads.
    """
    if op.kind == "package_install":
        item["type"] = _KIND_TO_ACTIVITY_TYPE[op.kind]
        package_id = (op.params or {}).get("package_id")
        package = (
            db.get(InstalledPackage, package_id) if package_id is not None else None
        )
        item["package_name"] = package.name if package else f"Package #{package_id}"
        from app.services.operations.package_facade import PackageInstallFacade

        job = PackageInstallFacade(db, op)
        item["has_logs"] = job_has_logs_by_policy(
            op,
            log_save_policy,
            output_text=[job.stdout, job.stderr, op.error_message],
            file_path=op.log_file_path,
            exit_code=job.exit_code,
        )
        return
    if op.kind == "backup":
        from app.services.operations.backup_facade import (
            BackupJobFacade,
            backup_job_has_logs,
        )

        job = BackupJobFacade(db, op)
        item["triggered_by"] = job.triggered_by
        item["backup_plan_id"] = job.backup_plan_id
        item["archive_name"] = job.archive_name
        item["archive_pruned_at"] = job.archive_pruned_at
        item["has_logs"] = backup_job_has_logs(db, job, log_save_policy=log_save_policy)
        if job.scheduled_job_id:
            scheduled_job = db.get(ScheduledJob, job.scheduled_job_id)
            item["schedule_name"] = scheduled_job.name if scheduled_job else None
        if job.backup_plan_id:
            plan = db.get(BackupPlan, job.backup_plan_id)
            item["backup_plan_name"] = plan.name if plan else None
        return
    if op.kind != "rclone_sync":
        return
    from app.services.operations.rclone_facade import (
        RcloneSyncFacade,
        rclone_activity_type,
    )

    job = RcloneSyncFacade(db, op)
    item["type"] = rclone_activity_type(job)
    item["triggered_by"] = job.triggered_by
    item["error_message"] = op.error_message or job.error_text
    item["has_logs"] = job_has_logs_by_policy(
        op,
        log_save_policy,
        output_text=[job.log_text, job.error_text],
        file_path=op.log_file_path,
    )


def _operation_activity_items(
    db: Session,
    *,
    current_user: User,
    limit: int,
    before: Optional[datetime],
    job_type: Optional[str],
    status: Optional[str],
    category: Optional[List[str]],
    trigger: Optional[List[str]],
    repository_id: Optional[int] = None,
    collapse_runs: bool,
    log_save_policy: str,
) -> List[dict]:
    """Read operations rows for the Activity union (spec 9.3).

    Index-category rows are hidden unless the category filter names them.
    With collapse_runs, follow-ups ride under their top-level parent and are
    shown whenever the parent is; without it every row is top level.
    """
    from app.api.operations import (
        accessible_repository_ids,
        _scope_to_accessible_repos,
    )

    q = _scope_to_accessible_repos(
        db.query(Operation), accessible_repository_ids(db, current_user)
    )
    if repository_id is not None:
        q = q.filter(Operation.repository_id == repository_id)
    if job_type:
        job_type_kind = operation_kind_for_activity_type(job_type)
        if job_type in RCLONE_ACTIVITY_OPERATIONS:
            # Both activity names live in one kind (spec 6.2); the sub-type is
            # on the details row, so filter the built items below instead.
            q = q.filter(Operation.kind == "rclone_sync")
        elif job_type_kind not in op_vocab.KINDS:
            return []
        else:
            q = q.filter(Operation.kind == job_type_kind)
    if status:
        wanted = {status, op_vocab.LEGACY_STATUS_MAP.get(status, status)}
        q = q.filter(Operation.status.in_(tuple(wanted)))
    if not category or "index" not in category:
        # Reconcile runs are index rows `_visible` hides unless the filter
        # names them, and they outnumber everything else many times over.
        # Keep them out of the window so it reaches back through real runs;
        # index follow-ups stay, they ride under their visible parent.
        q = q.filter(
            ~((Operation.category == "index") & (Operation.trigger != "followup"))
        )
    scoped = q
    if before is not None:
        q = q.filter(func.coalesce(Operation.started_at, Operation.created_at) < before)
    # Window by time, not id: rows backfilled from the legacy job tables
    # carry ids far above the backups they ran beside, so an id window kept
    # a plan's prune and dropped the backup it followed.
    ops = (
        q.order_by(
            func.coalesce(Operation.started_at, Operation.created_at).desc(),
            Operation.id.desc(),
        )
        .limit(limit * 4)
        .all()
    )
    if not ops:
        return []
    # Follow-ups are newer than what they follow, so the window's oldest
    # edge can hold a chain without its head. Pull the missing ancestors in,
    # under the same filters, so the chain rides under its run instead of
    # surfacing as loose steps.
    have = {op.id for op in ops}
    missing = {op.depends_on_id for op in ops if op.depends_on_id is not None} - have
    while missing:
        parents = scoped.filter(Operation.id.in_(tuple(missing))).all()
        ops.extend(parents)
        have |= {p.id for p in parents}
        missing = {
            p.depends_on_id for p in parents if p.depends_on_id is not None
        } - have
    repo_ids = {op.repository_id for op in ops if op.repository_id is not None}
    repos = (
        {
            r.id: r
            for r in db.query(Repository).filter(Repository.id.in_(repo_ids)).all()
        }
        if repo_ids
        else {}
    )
    by_id: dict[int, dict] = {}
    for op in ops:
        repo = repos.get(op.repository_id) if op.repository_id is not None else None
        item = serialize_operation(
            op,
            repository_name=repo.name if repo else None,
            repository_path=repo.path if repo else None,
            has_logs=job_has_logs_by_policy(
                op,
                log_save_policy,
                output_text=[op.error_message],
                file_path=op.log_file_path,
            ),
        )
        _apply_legacy_activity_shape(db, op, item, log_save_policy=log_save_policy)
        if (
            job_type
            and item["type"] != job_type
            and job_type in (RCLONE_ACTIVITY_OPERATIONS)
        ):
            continue
        item["_sort_at"] = op.started_at or op.created_at
        item["_depends_on_id"] = op.depends_on_id
        item["_trigger"] = op.trigger
        item["_run_id"] = op.run_id
        by_id[op.id] = item

    def _visible(item: dict) -> bool:
        if category:
            if item["category"] not in category:
                return False
        elif item["category"] == "index":
            return False
        if trigger and item["trigger"] not in trigger:
            return False
        return True

    def _root_id(item: dict) -> int:
        """The row an operation rides under: follow-ups ride under whatever
        they depend on, and the later steps of one run (a reconcile's
        history and stats steps after its archive sync) ride under the
        run's first step. Anything else is a row of its own."""
        seen: set[int] = set()
        while True:
            parent = by_id.get(item["_depends_on_id"])
            if parent is None or item["id"] in seen:
                return item["id"]
            if item["_trigger"] != "followup" and parent["_run_id"] != item["_run_id"]:
                return item["id"]
            seen.add(item["id"])
            item = parent

    top_level: List[dict] = []
    if collapse_runs:
        roots = {item["id"]: _root_id(item) for item in by_id.values()}
        top_ids: set[int] = set()
        for item in by_id.values():
            if roots[item["id"]] == item["id"] and _visible(item):
                top_level.append(item)
                top_ids.add(item["id"])
        for item in sorted(by_id.values(), key=lambda i: i["id"]):
            root_id = roots[item["id"]]
            if root_id != item["id"] and root_id in top_ids:
                by_id[root_id]["followups"].append(item)
    else:
        top_level = [item for item in by_id.values() if _visible(item)]
    for item in by_id.values():
        item.pop("_depends_on_id", None)
        item.pop("_trigger", None)
        item.pop("_run_id", None)
        for followup in item["followups"]:
            followup.pop("_sort_at", None)
    return top_level


@router.get("/recent", response_model=List[ActivityItem])
async def list_recent_activity(
    limit: int = 100,
    before: Optional[datetime] = None,
    job_type: Optional[str] = None,  # Filter by type: 'backup', 'restore', etc.
    status: Optional[str] = None,  # Filter by status: 'running', 'completed', 'failed'
    category: Optional[List[str]] = Query(default=None),
    trigger: Optional[List[str]] = Query(default=None),
    repository_id: Optional[int] = None,
    collapse_runs: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get recent activity across all job types.

    Returns a unified list of all operations sorted by start time (most recent first).
    Excludes the logs column for performance - use the logs endpoint to fetch logs.

    `repository_id` narrows every source in SQL, before each source's own
    limit, so one repository's history does not depend on how busy the rest
    of the install has been.
    """

    activities = []
    log_save_policy = get_log_save_policy(db)
    scoped_repository = (
        db.get(Repository, repository_id) if repository_id is not None else None
    )
    if repository_id is not None and scoped_repository is None:
        return []
    # Plan runs, availability skips, package installs, and script executions
    # belong to no single repository, so a repository view drops them.
    repository_scoped = repository_id is not None

    # Availability Plan skips are plan-run records, not backups: Borg was never
    # invoked, so they must be added independently to Activity.
    if (
        (not job_type or job_type == "availability_check")
        and (not status or status == "skipped")
        and not repository_scoped
    ):
        plan_skip_query = db.query(BackupPlanRun).filter(
            BackupPlanRun.status == "skipped",
            BackupPlanRun.trigger == "availability",
        )
        if before is not None:
            plan_skip_query = plan_skip_query.filter(
                func.coalesce(BackupPlanRun.completed_at, BackupPlanRun.created_at)
                < before
            )
        plan_skips = (
            plan_skip_query.order_by(
                BackupPlanRun.completed_at.desc(), BackupPlanRun.id.desc()
            )
            .limit(limit)
            .all()
        )
        for run in plan_skips:
            plan = (
                db.get(BackupPlan, run.backup_plan_id) if run.backup_plan_id else None
            )
            activities.append(
                {
                    "activity_key": f"backup-plan-run-{run.id}",
                    "id": run.id,
                    "type": "availability_check",
                    "status": "skipped",
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "error_message": run.error_message,
                    "repository": plan.name if plan else "Backup plan",
                    "repository_path": None,
                    "log_file_path": None,
                    "triggered_by": "backup_plan",
                    "backup_plan_id": run.backup_plan_id,
                    "backup_plan_run_id": run.id,
                    "backup_plan_name": plan.name if plan else None,
                    "skip_reason": run.skip_reason,
                    "has_logs": False,
                    "_sort_at": run.completed_at or run.created_at,
                }
            )

        automation_skip_query = db.query(AvailabilityScheduleSkip)
        if before is not None:
            automation_skip_query = automation_skip_query.filter(
                AvailabilityScheduleSkip.occurred_at < before
            )
        automation_skips = (
            automation_skip_query.order_by(
                AvailabilityScheduleSkip.occurred_at.desc(),
                AvailabilityScheduleSkip.id.desc(),
            )
            .limit(limit)
            .all()
        )
        for skip in automation_skips:
            schedule = db.get(ScheduledJob, skip.scheduled_job_id)
            activities.append(
                {
                    "activity_key": f"availability-schedule-skip-{skip.id}",
                    "id": skip.id,
                    "type": "availability_check",
                    "status": "skipped",
                    "started_at": skip.occurred_at,
                    "completed_at": skip.occurred_at,
                    "error_message": None,
                    "repository": schedule.name if schedule else "Backup automation",
                    "repository_path": None,
                    "log_file_path": None,
                    "triggered_by": "schedule",
                    "schedule_id": skip.scheduled_job_id,
                    "schedule_name": schedule.name if schedule else None,
                    "skip_reason": skip.reason,
                    "has_logs": False,
                    "_sort_at": skip.occurred_at,
                }
            )

    # A plan run that failed before its backups ran, or after they all
    # succeeded, has no operation of its own to say so: its error lives on the
    # run. Without this the feed shows the run's pre-backup hook alone and the
    # band reads as a success (a scheduled plan refused by admission, a hook
    # failure, a lost database).
    if (
        (not job_type or job_type == "backup_plan_run")
        and (not status or status == "failed")
        and not repository_scoped
    ):
        failed_run_query = db.query(BackupPlanRun).filter(
            BackupPlanRun.status == "failed"
        )
        if before is not None:
            failed_run_query = failed_run_query.filter(
                func.coalesce(BackupPlanRun.completed_at, BackupPlanRun.created_at)
                < before
            )
        failed_runs = (
            failed_run_query.order_by(
                BackupPlanRun.completed_at.desc(), BackupPlanRun.id.desc()
            )
            .limit(limit)
            .all()
        )
        # A run whose own operations failed already says so, in the same band
        # and with more detail. This row is for the failure they do not show.
        spoken_for = (
            {
                run_id
                for (run_id,) in db.query(Operation.backup_plan_run_id)
                .filter(
                    Operation.backup_plan_run_id.in_([r.id for r in failed_runs]),
                    Operation.status == "failed",
                )
                .distinct()
            }
            if failed_runs
            else set()
        )
        for run in failed_runs:
            if run.id in spoken_for:
                continue
            plan = (
                db.get(BackupPlan, run.backup_plan_id) if run.backup_plan_id else None
            )
            activities.append(
                {
                    "activity_key": f"backup-plan-run-failed-{run.id}",
                    "id": run.id,
                    "type": "backup_plan_run",
                    "status": "failed",
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "error_message": run.error_message,
                    "repository": plan.name if plan else "Backup plan",
                    "repository_path": None,
                    "log_file_path": None,
                    "triggered_by": "backup_plan",
                    "backup_plan_id": run.backup_plan_id,
                    "backup_plan_run_id": run.id,
                    "backup_plan_name": plan.name if plan else None,
                    "has_logs": False,
                    "_sort_at": run.completed_at or run.created_at,
                }
            )

    # Fetch script executions
    # Script executions name their repository, so a repository-scoped view
    # keeps the ones that ran against it instead of dropping the source.
    if not job_type or job_type == "script_execution":
        from app.api.operations import accessible_repository_ids

        script_query = db.query(ScriptExecution)
        # Same rule as operations: rows with no repository are system rows
        # every user may see; the rest need a permission on the repository.
        accessible = accessible_repository_ids(db, current_user)
        if accessible is not None:
            script_query = script_query.filter(
                ScriptExecution.repository_id.is_(None)
                | ScriptExecution.repository_id.in_(accessible)
            )
        if repository_scoped:
            script_query = script_query.filter(
                ScriptExecution.repository_id == repository_id
            )
        if status:
            script_query = script_query.filter(ScriptExecution.status == status)
        if before is not None:
            script_query = script_query.filter(ScriptExecution.started_at < before)
        script_executions = (
            script_query.order_by(ScriptExecution.started_at.desc()).limit(limit).all()
        )
        for execution in script_executions:
            script_name = _script_execution_display_name(execution)
            backup_plan_name = None
            if execution.backup_plan:
                backup_plan_name = execution.backup_plan.name
            repo_name = (
                execution.repository.name if execution.repository else script_name
            )
            repo_path = execution.repository.path if execution.repository else None
            activities.append(
                {
                    "id": execution.id,
                    "type": "script_execution",
                    "status": execution.status,
                    "started_at": execution.started_at,
                    "completed_at": execution.completed_at,
                    "error_message": execution.error_message,
                    "repository": repo_name,
                    "repository_path": repo_path,
                    "repository_id": execution.repository_id,
                    "operation_id": execution.operation_id,
                    "hook_type": execution.hook_type,
                    "log_file_path": None,
                    "triggered_by": execution.triggered_by or "manual",
                    "schedule_id": None,
                    "schedule_name": None,
                    "backup_plan_id": execution.backup_plan_id,
                    "backup_plan_run_id": execution.backup_plan_run_id,
                    "backup_plan_name": backup_plan_name,
                    "archive_name": execution.hook_type,
                    "package_name": script_name,
                    "has_logs": job_has_logs_by_policy(
                        execution,
                        log_save_policy,
                        output_text=[
                            execution.stdout,
                            execution.stderr,
                            execution.error_message,
                        ],
                        exit_code=execution.exit_code,
                    ),
                    "_sort_at": execution.started_at,
                }
            )

    # The non-operation sources (availability skips and script executions)
    # carry no operations axes of their own, so derive them before the filters
    # apply, then union in the operations rows (spec 9.3).
    for activity in activities:
        activity.setdefault(
            "category", _category_for_non_operation_type(activity["type"])
        )
        activity.setdefault("trigger", _trigger_for_non_operation_item(activity))
        activity.setdefault("followups", [])
    activities.extend(
        _operation_activity_items(
            db,
            current_user=current_user,
            limit=limit,
            before=before,
            job_type=job_type,
            status=status,
            category=category,
            trigger=trigger,
            repository_id=repository_id,
            collapse_runs=collapse_runs,
            log_save_policy=log_save_policy,
        )
    )

    # A pre- or post-backup script ran around one backup, so it rides under
    # that backup (like the follow-up chain) when the backup is in the list,
    # and reads as part of the run rather than a manual script beside it.
    if collapse_runs:
        parents = {a["id"]: a for a in activities if a.get("kind") is not None}
        top_level: List[dict] = []
        for activity in activities:
            parent = (
                parents.get(activity.get("operation_id"))
                if activity["type"] == "script_execution"
                else None
            )
            if parent is None:
                top_level.append(activity)
                continue
            activity["trigger"] = parent.get("trigger", activity["trigger"])
            activity.pop("_sort_at", None)
            parent["followups"].append(activity)
        activities = top_level

    # The category and trigger filters apply to top-level rows only, after
    # hooks have found their backup: a hook is a system row with its own
    # trigger, and it must ride under a backup selected by category before
    # the filter would drop it. Operation rows already passed these filters.
    if category:
        activities = [a for a in activities if a["category"] in category]
    if trigger:
        activities = [a for a in activities if a["trigger"] in trigger]

    # Sort by start time, falling back to creation time for pending jobs.
    activities.sort(
        key=lambda x: x.get("_sort_at") or x["started_at"] or datetime.min,
        reverse=True,
    )

    # Apply limit to combined results
    activities = activities[:limit]
    for activity in activities:
        activity["sort_at"] = activity.pop("_sort_at", None) or activity["started_at"]

    return activities


@router.get("/{job_type}/{job_id}/logs")
async def get_job_logs(
    job_type: str,
    job_id: int,
    offset: int = 0,
    limit: int = 500,  # Default to 500 lines per request
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get logs for a specific job.

    Supports streaming logs from file (for running jobs) or returning stored logs.
    Returns max 500 lines per request to prevent performance issues.
    """

    # Map job type to model
    job_models = {
        "script_execution": ScriptExecution,
    }

    if _is_operation_only_kind(job_type, job_models):
        op = _get_operation_or_404(db, job_type, job_id, current_user)
        if (
            job_type == "backup"
            and op.status == "running"
            and op.execution_mode != "agent"
        ):
            # An agent backup streams its `agent_job_logs` lines instead; the
            # in-memory buffer below belongs to the server's own borg process.
            return _running_backup_log_response(job_id, offset, limit)
        sources = _operation_log_sources(db, job_type, op)
        # A backup answers for itself, since agent log lines count toward the
        # policy exactly as the legacy branch's `_backup_job_has_logs` had it.
        if not sources.get(
            "has_logs",
            job_has_logs_by_policy(
                op,
                get_log_save_policy(db),
                output_text=sources["output_text"],
                file_path=sources["file_path"],
                exit_code=sources["exit_code"],
            ),
        ):
            raise _no_logs_available_exception()
        return _paginate_log_text(sources["text"], offset, limit)

    if job_type == "script_execution":
        execution = (
            db.query(ScriptExecution).filter(ScriptExecution.id == job_id).first()
        )
        if not execution:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.activity.jobNotFound",
                    "params": {"jobType": job_type},
                },
            )
        _ensure_activity_logs_visible(job_type, execution, db)
        # While an agent hook runs, stream its live agent_job_logs (the terminal
        # stdout/stderr are only captured at completion); afterwards serve the
        # captured result.
        if execution.status == "running" and execution.agent_job_id is not None:
            log_text = _format_running_agent_script_logs(execution, db)
        else:
            log_text = _format_script_execution_logs(execution)
        return _paginate_log_text(log_text, offset, limit)

    if job_type in RCLONE_ACTIVITY_OPERATIONS:
        job = _get_rclone_job(db, job_type, job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.activity.jobNotFound",
                    "params": {"jobType": job_type},
                },
            )
        _ensure_activity_logs_visible(job_type, job, db)
        log_text = _format_rclone_job_logs(job)
        if log_text:
            return _paginate_log_text(log_text, offset, limit)
        if job.status in {"pending", "running"}:
            return _paginate_log_text(
                f"Cloud storage job is {job.status}...", offset, limit
            )
        return {"lines": [], "total_lines": 0, "has_more": False}

    if job_type not in job_models:
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.activity.invalidJobType",
                "params": {"jobType": job_type},
            },
        )

    job_model = job_models[job_type]
    job = db.query(job_model).filter(job_model.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "key": "backend.errors.activity.jobNotFound",
                "params": {"jobType": job_type},
            },
        )

    _ensure_activity_logs_visible(job_type, job, db)

    if job_type == "package":
        return _paginate_log_text(_format_package_install_logs(job), offset, limit)

    if job_type == "backup" and getattr(job, "execution_mode", None) == "agent":
        agent_job = _get_agent_job_for_backup(db, job.id)
        if not agent_job:
            return {"lines": [], "total_lines": 0, "has_more": False}

        lines = _get_agent_log_lines(db, agent_job.id)
        total_lines = len(lines)
        end_offset = min(offset + limit, total_lines)
        chunk = lines[offset:end_offset]
        return {
            "lines": [
                {"line_number": offset + i + 1, "content": line}
                for i, line in enumerate(chunk)
            ],
            "total_lines": total_lines,
            "has_more": end_offset < total_lines,
        }

    # For completed/failed jobs, prefer log_file_path (full borg output) over logs (hooks only)
    if job.status in ["completed", "failed", "completed_with_warnings"]:
        # First try reading from log file (contains all borg output)
        log_file_path = getattr(job, "log_file_path", None)
        if log_file_path and os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r") as f:
                    # EFFICIENT: Count total lines first without loading into memory
                    f.seek(0)
                    total_lines = sum(1 for _ in f)

                    # Reset to beginning and skip to offset
                    f.seek(0)
                    for _ in range(offset):
                        next(f, None)

                    # Read only the requested chunk
                    chunk = []
                    for i, line in enumerate(f):
                        if i >= limit:
                            break
                        chunk.append(line.rstrip())

                    end_offset = offset + len(chunk)

                    return {
                        "lines": [
                            {"line_number": offset + i + 1, "content": line}
                            for i, line in enumerate(chunk)
                        ],
                        "total_lines": total_lines,
                        "has_more": end_offset < total_lines,
                    }
            except Exception as e:
                # If file read fails, fall through to stored logs
                logger.warning(
                    "Failed to read log file, falling back to stored logs",
                    job_type=job_type,
                    job_id=job_id,
                    error=str(e),
                )

        # Fallback to stored logs in database (hooks or error messages)
        stored_logs = getattr(job, "logs", None)
        if stored_logs:
            lines = stored_logs.split("\n")
            total_lines = len(lines)

            # Apply offset and limit
            end_offset = min(offset + limit, total_lines)
            chunk = lines[offset:end_offset]

            return {
                "lines": [
                    {"line_number": offset + i + 1, "content": line}
                    for i, line in enumerate(chunk)
                ],
                "total_lines": total_lines,
                "has_more": end_offset < total_lines,
            }

    # For running jobs without log files (backup, check, compact), show progress message
    if job.status == "running":
        if job_type == "backup":
            return _running_backup_log_response(job_id, offset, limit)
        elif job_type in ["check", "restore_check", "compact"]:
            # Check/compact show progress message
            progress_msg = getattr(job, "progress_message", None)
            if progress_msg:
                lines = [
                    f"Job is currently running...",
                    f"",
                    f"Current progress: {progress_msg}",
                    f"",
                    f"Full logs will be available after the job completes.",
                ]
            else:
                lines = [
                    f"Job is currently running...",
                    f"",
                    f"Full logs will be available after the job completes.",
                ]
        else:
            lines = ["Job is currently running..."]

        return {
            "lines": [
                {"line_number": i + 1, "content": line} for i, line in enumerate(lines)
            ],
            "total_lines": len(lines),
            "has_more": False,
        }

    # If job is running and has log file, stream from file
    log_file_path = getattr(job, "log_file_path", None)
    if log_file_path and os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r") as f:
                lines = f.readlines()
                total_lines = len(lines)

                # For running jobs, if offset is 0, get last 500 lines + new ones
                # This prevents loading huge log files into memory
                if offset == 0 and total_lines > limit:
                    start_offset = total_lines - limit
                    chunk = lines[start_offset:]
                    return {
                        "lines": [
                            {
                                "line_number": start_offset + i + 1,
                                "content": line.rstrip(),
                            }
                            for i, line in enumerate(chunk)
                        ],
                        "total_lines": total_lines,
                        "has_more": False,  # For running jobs, we only show tail
                    }

                # Normal pagination
                end_offset = min(offset + limit, total_lines)
                chunk = lines[offset:end_offset]

                return {
                    "lines": [
                        {"line_number": offset + i + 1, "content": line.rstrip()}
                        for i, line in enumerate(chunk)
                    ],
                    "total_lines": total_lines,
                    "has_more": end_offset < total_lines,
                }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to read log file: {str(e)}"
            )

    error_message = getattr(job, "error_message", None)
    if error_message:
        lines = [str(error_message)]
        return {
            "lines": [
                {"line_number": i + 1, "content": line} for i, line in enumerate(lines)
            ],
            "total_lines": len(lines),
            "has_more": False,
        }

    # No logs available
    return {"lines": [], "total_lines": 0, "has_more": False}


@router.get("/{job_type}/{job_id}/logs/download")
async def download_job_logs(
    job_type: str,
    job_id: int,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    """Download logs for a specific job as a file."""
    # Map job type to model
    job_models = {
        "script_execution": ScriptExecution,
    }

    if _is_operation_only_kind(job_type, job_models):
        op = _get_operation_or_404(db, job_type, job_id, current_user)
        # Same policy gate as the paginated route above, so a download cannot
        # serve logs the log view reports as absent.
        sources = _operation_log_sources(db, job_type, op)
        # A backup answers for itself, since agent log lines count toward the
        # policy exactly as the legacy branch's `_backup_job_has_logs` had it.
        if not sources.get(
            "has_logs",
            job_has_logs_by_policy(
                op,
                get_log_save_policy(db),
                output_text=sources["output_text"],
                file_path=sources["file_path"],
                exit_code=sources["exit_code"],
            ),
        ):
            raise _no_logs_available_exception()
        if op.status in ("running", "installing"):
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.activity.cannotDownloadLogsForRunningJob"
                },
            )
        file_path = sources["file_path"]
        if job_type != "package" and file_path and os.path.exists(file_path):
            return FileResponse(
                file_path,
                media_type="text/plain",
                filename=f"operation_{op.id}.log",
            )
        # A pre-phase-5 legacy row mirrored its output into `logs` with no
        # file at all, and a package log file holds both streams behind
        # sentinels, so the rendered text is what a reader wants.
        text = sources["text"]
        if not text:
            raise _no_logs_available_exception()
        return _text_download_response(text, filename=f"operation_{op.id}_logs.txt")

    if job_type == "script_execution":
        execution = (
            db.query(ScriptExecution).filter(ScriptExecution.id == job_id).first()
        )
        if not execution:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.activity.jobNotFound",
                    "params": {"jobType": job_type},
                },
            )
        if execution.status == "running":
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.activity.cannotDownloadLogsForRunningJob"
                },
            )
        _ensure_activity_logs_visible(job_type, execution, db)
        log_text = _format_script_execution_logs(execution)
        if not log_text.strip():
            raise _no_logs_available_exception()
        return _text_download_response(
            log_text,
            filename=f"{job_type}_job_{job_id}_logs.txt",
        )

    if job_type in RCLONE_ACTIVITY_OPERATIONS:
        job = _get_rclone_job(db, job_type, job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.activity.jobNotFound",
                    "params": {"jobType": job_type},
                },
            )
        if job.status == "running":
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.activity.cannotDownloadLogsForRunningJob"
                },
            )
        _ensure_activity_logs_visible(job_type, job, db)
        if job.log_path and os.path.exists(job.log_path):
            return FileResponse(
                path=job.log_path,
                filename=f"{job_type}_job_{job_id}_logs.txt",
                media_type="text/plain",
            )
        log_text = _format_rclone_job_logs(job)
        if not log_text.strip():
            raise _no_logs_available_exception()
        return _text_download_response(
            log_text,
            filename=f"{job_type}_job_{job_id}_logs.txt",
        )

    if job_type not in job_models:
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.activity.invalidJobType",
                "params": {"jobType": job_type},
            },
        )

    job_model = job_models[job_type]
    job = db.query(job_model).filter(job_model.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "key": "backend.errors.activity.jobNotFound",
                "params": {"jobType": job_type},
            },
        )

    # Don't allow downloading logs for running jobs
    if job.status == "running":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.activity.cannotDownloadLogsForRunningJob"},
        )

    _ensure_activity_logs_visible(job_type, job, db)

    if job_type == "package":
        log_text = _format_package_install_logs(job)
        if not log_text.strip():
            raise _no_logs_available_exception()
        return _text_download_response(
            log_text,
            filename=f"{job_type}_job_{job_id}_logs.txt",
        )

    # Try to get logs from log file first
    log_file_path = getattr(job, "log_file_path", None)
    if log_file_path and os.path.exists(log_file_path):
        return FileResponse(
            path=log_file_path,
            filename=f"{job_type}_job_{job_id}_logs.txt",
            media_type="text/plain",
        )

    # Fallback to database logs
    if hasattr(job, "logs") and job.logs:
        # Create temp file with logs
        temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
        try:
            temp_file.write(job.logs)
            temp_file.flush()
            temp_file.close()

            return FileResponse(
                path=temp_file.name,
                filename=f"{job_type}_job_{job_id}_logs.txt",
                media_type="text/plain",
            )
        except Exception as e:
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise e

    if job_type == "backup" and getattr(job, "execution_mode", None) == "agent":
        agent_job = _get_agent_job_for_backup(db, job.id)
        if agent_job:
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            )
            try:
                temp_file.write("\n".join(_get_agent_log_lines(db, agent_job.id)))
                temp_file.flush()
                temp_file.close()
                return FileResponse(
                    path=temp_file.name,
                    filename=f"{job_type}_job_{job_id}_logs.txt",
                    media_type="text/plain",
                )
            except Exception as e:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                raise e

    # No logs available
    raise _no_logs_available_exception()


@router.delete("/{job_type}/{job_id}")
async def delete_job(
    job_type: str,
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a job entry and its associated log files.

    Only admin users can delete job entries.
    Cannot delete running or pending jobs.
    """

    # Check if user is admin
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "backend.errors.activity.adminOnlyDelete"},
        )

    # Map job type to model
    job_models = {
        "script_execution": ScriptExecution,
    }

    if _is_operation_only_kind(job_type, job_models):
        op = _get_operation_or_404(db, job_type, job_id, current_user)
        if op.status == "running":
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.activity.cannotDeleteRunningJob"},
            )
        op_log_path = getattr(op, "log_file_path", None)
        if op_log_path and os.path.exists(op_log_path):
            try:
                os.remove(op_log_path)
            except Exception as e:
                logger.warning(
                    f"Failed to delete log file for operation {job_id}",
                    path=op_log_path,
                    error=str(e),
                )
        db.delete(op)
        db.commit()
        logger.info(
            f"Deleted {job_type} operation {job_id} by admin user",
            admin_user=current_user.username,
        )
        return {
            "success": True,
            "message": "backend.success.activity.jobDeleted",
            "job_id": job_id,
            "job_type": job_type,
        }

    if job_type in RCLONE_ACTIVITY_OPERATIONS:
        job = _get_rclone_job(db, job_type, job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.activity.jobNotFound",
                    "params": {"jobType": job_type},
                },
            )
        if job.status == "running":
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.activity.cannotDeleteRunningJob"},
            )
        if job.log_path and os.path.exists(job.log_path):
            try:
                os.remove(job.log_path)
                logger.info(
                    f"Deleted log file for {job_type} job {job_id}",
                    path=job.log_path,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to delete log file for {job_type} job {job_id}",
                    path=job.log_path,
                    error=str(e),
                )
        try:
            # `job` is the facade; the row it presents is the operation.
            db.delete(db.get(Operation, job.id))
            db.commit()
            logger.info(
                f"Deleted {job_type} job {job_id} by admin user",
                admin_user=current_user.username,
            )
            return {
                "success": True,
                "message": "backend.success.activity.jobDeleted",
                "job_id": job_id,
                "job_type": job_type,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete {job_type} job {job_id}", error=str(e))
            raise HTTPException(
                status_code=500, detail=f"Failed to delete job: {str(e)}"
            )

    if job_type not in job_models:
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.activity.invalidJobType",
                "params": {"jobType": job_type},
            },
        )

    job_model = job_models[job_type]
    job = db.query(job_model).filter(job_model.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "key": "backend.errors.activity.jobNotFound",
                "params": {"jobType": job_type.capitalize()},
            },
        )

    # Prevent deletion of running jobs (allow pending to clean up stuck jobs)
    if job.status == "running":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.activity.cannotDeleteRunningJob"},
        )

    # Delete log file if it exists
    log_file_path = getattr(job, "log_file_path", None)
    if log_file_path and os.path.exists(log_file_path):
        try:
            os.remove(log_file_path)
            logger.info(
                f"Deleted log file for {job_type} job {job_id}", path=log_file_path
            )
        except Exception as e:
            logger.warning(
                f"Failed to delete log file for {job_type} job {job_id}",
                path=log_file_path,
                error=str(e),
            )
            # Continue with job deletion even if log file deletion fails

    # Delete the job from database
    try:
        db.delete(job)
        db.commit()
        logger.info(
            f"Deleted {job_type} job {job_id} by admin user",
            admin_user=current_user.username,
        )

        return {
            "success": True,
            "message": "backend.success.activity.jobDeleted",
            "job_id": job_id,
            "job_type": job_type,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete {job_type} job {job_id}", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")
