"""
Activity feed API endpoints.

Provides a unified view of all operations (backups, restores, checks, compacts, package installs).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
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
    BackupJob,
    BackupPlan,
    RestoreJob,
    CheckJob,
    CompactJob,
    PruneJob,
    RestoreCheckJob,
    PackageInstallJob,
    Repository,
    RcloneSyncJob,
    InstalledPackage,
    ScheduledJob,
    ScriptExecution,
)
from app.api.auth import get_current_user, User
from app.core.security import get_current_download_user
from app.utils.datetime_utils import serialize_datetime
from app.services.backup_service import backup_service
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy

logger = structlog.get_logger()

router = APIRouter(prefix="/api/activity", tags=["activity"])


def _get_agent_job_for_backup(db: Session, backup_job_id: int) -> Optional[AgentJob]:
    return (
        db.query(AgentJob)
        .filter(AgentJob.backup_job_id == backup_job_id)
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

    # Type-specific metadata
    archive_name: Optional[str] = None  # For backup/restore
    package_name: Optional[str] = None  # For package installs
    has_logs: bool = False  # Whether logs are available for download
    repository_path: Optional[str] = (
        None  # Full repository path (for mapping to friendly name)
    )

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


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


RCLONE_ACTIVITY_OPERATIONS = {
    "rclone_sync": "sync",
    "rclone_hydrate": "hydrate",
}


def _no_logs_available_exception() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"key": "backend.errors.activity.noLogsAvailableForJob"},
    )


def _format_rclone_job_logs(job: RcloneSyncJob) -> str:
    parts = []
    if job.log_text:
        parts.append(job.log_text)
    if job.error_text and job.error_text not in (job.log_text or ""):
        parts.append(job.error_text)
    return "\n".join(parts)


def _format_package_install_logs(job: PackageInstallJob) -> str:
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


def _get_rclone_job(db: Session, job_type: str, job_id: int) -> RcloneSyncJob | None:
    operation = RCLONE_ACTIVITY_OPERATIONS[job_type]
    return (
        db.query(RcloneSyncJob)
        .filter(RcloneSyncJob.id == job_id, RcloneSyncJob.operation == operation)
        .first()
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
        )
    except Exception as e:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        raise e


@router.get("/recent", response_model=List[ActivityItem])
async def list_recent_activity(
    limit: int = 200,
    job_type: Optional[str] = None,  # Filter by type: 'backup', 'restore', etc.
    status: Optional[str] = None,  # Filter by status: 'running', 'completed', 'failed'
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get recent activity across all job types.

    Returns a unified list of all operations sorted by start time (most recent first).
    Excludes the logs column for performance - use the logs endpoint to fetch logs.
    """

    activities = []
    log_save_policy = get_log_save_policy(db)

    # Fetch backup jobs
    if not job_type or job_type == "backup":
        backup_jobs = (
            db.query(BackupJob).order_by(BackupJob.started_at.desc()).limit(limit).all()
        )
        for job in backup_jobs:
            if status and job.status != status:
                continue
            # Get repository name from path
            repo = (
                db.query(Repository).filter(Repository.path == job.repository).first()
            )
            repo_name = repo.name if repo else job.repository

            # Determine trigger type
            triggered_by = (
                "backup_plan"
                if job.backup_plan_id
                else "schedule"
                if job.scheduled_job_id
                else "manual"
            )

            # Get schedule name if this is a scheduled backup
            schedule_name = None
            if job.scheduled_job_id:
                scheduled_job = (
                    db.query(ScheduledJob)
                    .filter(ScheduledJob.id == job.scheduled_job_id)
                    .first()
                )
                if scheduled_job:
                    schedule_name = scheduled_job.name
            backup_plan_name = None
            if job.backup_plan_id:
                backup_plan = (
                    db.query(BackupPlan)
                    .filter(BackupPlan.id == job.backup_plan_id)
                    .first()
                )
                if backup_plan:
                    backup_plan_name = backup_plan.name

            activities.append(
                {
                    "id": job.id,
                    "type": "backup",
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                    "repository": repo_name,
                    "repository_path": job.repository,  # Always include the path
                    "log_file_path": job.log_file_path,
                    "triggered_by": triggered_by,
                    "schedule_id": job.scheduled_job_id,
                    "schedule_name": schedule_name,
                    "backup_plan_id": job.backup_plan_id,
                    "backup_plan_run_id": job.backup_plan_run_id,
                    "backup_plan_name": backup_plan_name,
                    "archive_name": getattr(job, "archive_name", None),
                    "package_name": None,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[job.logs, job.error_message],
                        file_path=job.log_file_path,
                    ),
                }
            )

    # Fetch restore jobs
    if not job_type or job_type == "restore":
        restore_jobs = (
            db.query(RestoreJob)
            .order_by(RestoreJob.started_at.desc())
            .limit(limit)
            .all()
        )
        for job in restore_jobs:
            if status and job.status != status:
                continue
            # Get repository name from path
            repo = (
                db.query(Repository).filter(Repository.path == job.repository).first()
            )
            repo_name = repo.name if repo else job.repository

            activities.append(
                {
                    "id": job.id,
                    "type": "restore",
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                    "repository": repo_name,
                    "repository_path": job.repository,  # Always include the path
                    "log_file_path": None,  # Restore jobs store logs in DB, not file
                    "triggered_by": "manual",  # Restore jobs are always manual
                    "schedule_id": None,
                    "archive_name": job.archive,
                    "package_name": None,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[job.logs, job.error_message],
                    ),
                }
            )

    # Fetch check jobs
    if not job_type or job_type == "check":
        check_jobs = db.query(CheckJob).order_by(CheckJob.id.desc()).limit(limit).all()
        for job in check_jobs:
            if status and job.status != status:
                continue
            # Get repository name from repository_id, with fallback to stored path
            repo = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )
            repo_name = repo.name if repo else f"Repository #{job.repository_id}"
            repo_path = repo.path if repo else job.repository_path
            triggered_by = (
                "schedule" if getattr(job, "scheduled_check", False) else "manual"
            )

            activities.append(
                {
                    "id": job.id,
                    "type": "check",
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                    "repository": repo_name,
                    "repository_path": repo_path,
                    "log_file_path": getattr(job, "log_file_path", None),
                    "triggered_by": triggered_by,
                    "schedule_id": None,
                    "archive_name": None,
                    "package_name": None,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[
                            getattr(job, "logs", None),
                            job.error_message,
                        ],
                        file_path=getattr(job, "log_file_path", None),
                    ),
                    "_sort_at": job.started_at or job.created_at,
                }
            )

    # Fetch restore check jobs
    if not job_type or job_type == "restore_check":
        restore_check_jobs = (
            db.query(RestoreCheckJob)
            .order_by(RestoreCheckJob.id.desc())
            .limit(limit)
            .all()
        )
        for job in restore_check_jobs:
            if status and job.status != status:
                continue
            repo = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )
            repo_name = repo.name if repo else f"Repository #{job.repository_id}"
            repo_path = repo.path if repo else job.repository_path
            triggered_by = (
                "schedule"
                if getattr(job, "scheduled_restore_check", False)
                else "manual"
            )

            activities.append(
                {
                    "id": job.id,
                    "type": "restore_check",
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                    "repository": repo_name,
                    "repository_path": repo_path,
                    "log_file_path": getattr(job, "log_file_path", None),
                    "triggered_by": triggered_by,
                    "schedule_id": None,
                    "archive_name": job.archive_name,
                    "package_name": None,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[
                            getattr(job, "logs", None),
                            job.error_message,
                        ],
                        file_path=getattr(job, "log_file_path", None),
                    ),
                    "_sort_at": job.started_at or job.created_at,
                }
            )

    # Fetch compact jobs
    if not job_type or job_type == "compact":
        compact_jobs = (
            db.query(CompactJob)
            .order_by(CompactJob.started_at.desc())
            .limit(limit)
            .all()
        )
        for job in compact_jobs:
            if status and job.status != status:
                continue
            # Get repository name from repository_id, with fallback to stored path
            repo = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )
            repo_name = repo.name if repo else f"Repository #{job.repository_id}"
            repo_path = repo.path if repo else job.repository_path

            # Determine trigger type based on scheduled_compact field
            triggered_by = (
                "schedule" if getattr(job, "scheduled_compact", False) else "manual"
            )

            activities.append(
                {
                    "id": job.id,
                    "type": "compact",
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                    "repository": repo_name,
                    "repository_path": repo_path,
                    "log_file_path": getattr(job, "log_file_path", None),
                    "triggered_by": triggered_by,
                    "schedule_id": None,
                    "archive_name": None,
                    "package_name": None,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[
                            getattr(job, "logs", None),
                            job.error_message,
                        ],
                        file_path=getattr(job, "log_file_path", None),
                    ),
                }
            )

    # Fetch prune jobs
    if not job_type or job_type == "prune":
        prune_jobs = (
            db.query(PruneJob).order_by(PruneJob.started_at.desc()).limit(limit).all()
        )
        for job in prune_jobs:
            if status and job.status != status:
                continue
            # Get repository name from repository_id, with fallback to stored path
            repo = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )
            repo_name = repo.name if repo else f"Repository #{job.repository_id}"
            repo_path = repo.path if repo else job.repository_path

            # Determine trigger type based on scheduled_prune field
            triggered_by = (
                "schedule" if getattr(job, "scheduled_prune", False) else "manual"
            )

            activities.append(
                {
                    "id": job.id,
                    "type": "prune",
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                    "repository": repo_name,
                    "repository_path": repo_path,
                    "log_file_path": getattr(job, "log_file_path", None),
                    "triggered_by": triggered_by,
                    "schedule_id": None,
                    "archive_name": None,
                    "package_name": None,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[
                            getattr(job, "logs", None),
                            job.error_message,
                        ],
                        file_path=getattr(job, "log_file_path", None),
                    ),
                }
            )

    # Fetch package install jobs
    if not job_type or job_type == "package":
        package_jobs = (
            db.query(PackageInstallJob)
            .order_by(PackageInstallJob.started_at.desc())
            .limit(limit)
            .all()
        )
        for job in package_jobs:
            if status and job.status != status:
                continue
            # Get package name from package_id
            package = (
                db.query(InstalledPackage)
                .filter(InstalledPackage.id == job.package_id)
                .first()
            )
            package_name = package.name if package else f"Package #{job.package_id}"

            activities.append(
                {
                    "id": job.id,
                    "type": "package",
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_message,
                    "repository": None,
                    "log_file_path": getattr(job, "log_file_path", None),
                    "triggered_by": "manual",  # Package jobs are always manual
                    "schedule_id": None,
                    "archive_name": None,
                    "package_name": package_name,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[
                            getattr(job, "stdout", None),
                            getattr(job, "stderr", None),
                            job.error_message,
                        ],
                        file_path=getattr(job, "log_file_path", None),
                    ),
                }
            )

    # Fetch script executions
    if not job_type or job_type == "script_execution":
        script_executions = (
            db.query(ScriptExecution)
            .order_by(ScriptExecution.started_at.desc())
            .limit(limit)
            .all()
        )
        for execution in script_executions:
            if status and execution.status != status:
                continue
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

    if not job_type or job_type in RCLONE_ACTIVITY_OPERATIONS:
        operations = (
            [RCLONE_ACTIVITY_OPERATIONS[job_type]]
            if job_type in RCLONE_ACTIVITY_OPERATIONS
            else list(RCLONE_ACTIVITY_OPERATIONS.values())
        )
        rclone_jobs = (
            db.query(RcloneSyncJob)
            .filter(RcloneSyncJob.operation.in_(operations))
            .order_by(RcloneSyncJob.id.desc())
            .limit(limit)
            .all()
        )
        for job in rclone_jobs:
            if status and job.status != status:
                continue
            repo = (
                db.query(Repository).filter(Repository.id == job.repository_id).first()
            )
            repo_name = repo.name if repo else f"Repository #{job.repository_id}"
            repo_path = repo.path if repo else None
            activity_type = (
                "rclone_hydrate" if job.operation == "hydrate" else "rclone_sync"
            )
            activities.append(
                {
                    "id": job.id,
                    "type": activity_type,
                    "status": job.status,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "error_message": job.error_text,
                    "repository": repo_name,
                    "repository_path": repo_path,
                    "log_file_path": job.log_path,
                    "triggered_by": job.triggered_by,
                    "schedule_id": None,
                    "archive_name": None,
                    "package_name": None,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[job.log_text, job.error_text],
                        file_path=job.log_path,
                    ),
                    "_sort_at": job.started_at or job.created_at,
                }
            )

    # Sort by start time, falling back to creation time for pending jobs.
    activities.sort(
        key=lambda x: x.get("_sort_at") or x["started_at"] or datetime.min,
        reverse=True,
    )

    # Apply limit to combined results
    activities = activities[:limit]
    for activity in activities:
        activity.pop("_sort_at", None)

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
        "backup": BackupJob,
        "restore": RestoreJob,
        "check": CheckJob,
        "restore_check": RestoreCheckJob,
        "compact": CompactJob,
        "prune": PruneJob,
        "package": PackageInstallJob,
        "script_execution": ScriptExecution,
    }

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
        return _paginate_log_text(
            _format_script_execution_logs(execution), offset, limit
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
            # For running backups, try to get log buffer (last 500 lines)
            log_buffer, buffer_exists = backup_service.get_log_buffer(
                job_id, tail_lines=500
            )

            logger.info(
                "Retrieved log buffer for running backup",
                job_id=job_id,
                buffer_exists=buffer_exists,
                buffer_length=len(log_buffer),
                buffer_type=type(log_buffer).__name__,
            )

            # Check if buffer exists (True means buffer was created, even if empty)
            # Empty buffer means backup started but no logs output yet
            if buffer_exists:
                if len(log_buffer) > 0:
                    # Return last 500 lines from in-memory buffer
                    response = {
                        "lines": [
                            {"line_number": i + 1, "content": line}
                            for i, line in enumerate(log_buffer)
                        ],
                        "total_lines": len(log_buffer),
                        "has_more": False,  # Always show tail for running jobs
                    }
                    logger.info(
                        "Returning log buffer data",
                        job_id=job_id,
                        lines_count=len(response["lines"]),
                        first_line=log_buffer[0] if log_buffer else None,
                    )
                    return response
                else:
                    # Buffer exists but empty - backup command started, waiting for first output
                    if offset > 0:
                        return {"lines": [], "total_lines": 0, "has_more": False}
                    logger.info(
                        "Buffer exists but empty, returning processing message",
                        job_id=job_id,
                    )
                    lines = [
                        "Backup is running...",
                        "",
                        "Processing started, waiting for first log output...",
                        "",
                        "Note: Showing last 500 lines from in-memory buffer. Full logs not saved to disk.",
                    ]
            else:
                # Buffer not created yet - backup job hasn't started borg command
                if offset > 0:
                    return {"lines": [], "total_lines": 0, "has_more": False}
                logger.info(
                    "Buffer not created yet, returning waiting message", job_id=job_id
                )
                lines = [
                    "Backup is currently running...",
                    "",
                    "Waiting for logs...",
                    "",
                    "Note: Showing last 500 lines from in-memory buffer. Full logs not saved to disk.",
                ]
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
        "backup": BackupJob,
        "restore": RestoreJob,
        "check": CheckJob,
        "restore_check": RestoreCheckJob,
        "compact": CompactJob,
        "prune": PruneJob,
        "package": PackageInstallJob,
        "script_execution": ScriptExecution,
    }

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
        "backup": BackupJob,
        "restore": RestoreJob,
        "check": CheckJob,
        "restore_check": RestoreCheckJob,
        "compact": CompactJob,
        "prune": PruneJob,
        "package": PackageInstallJob,
        "script_execution": ScriptExecution,
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
