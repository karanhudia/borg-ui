from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog
import json
from types import SimpleNamespace
from typing import Any, Optional
from datetime import datetime

from app.database.database import get_db
from app.database.models import (
    AgentJobLog,
    User,
    BackupJob,
    BackupPlan,
    OperationBackupRetryLineage,
    Repository,
    CheckJob,
    PruneJob,
    CompactJob,
)
from app.config import settings
from app.core.security import (
    get_current_user,
    get_current_download_user,
    check_repo_access,
)
from app.services.backup_service import backup_service
from app.services.backup_progress_contract import serialize_backup_progress_details
from app.services.job_admission import (
    OPERATION_BACKUP,
    ensure_manual_backup_capacity,
    ensure_repository_admission,
)
from app.services.log_policy import get_log_save_policy
from app.services.operations.backup_facade import (
    CANCELLED_BY_USER,
    CANCELLED_PROCESS_NOT_FOUND,
    backup_job_has_logs,
    create_backup_operation,
    is_backup_operation,
    list_backup_jobs,
    resolve_backup_job,
)
from app.services.operations.enqueue import wake_runner
from app.services.operations.runner import operation_runner
from app.services.repository_executor import (
    cancel_agent_backup_job,
    get_agent_job_for_backup,
    is_agent_executor,
    validate_agent_backup_repository,
)
from app.utils.backup_maintenance import RUNNING_BACKUP_MAINTENANCE_FAILURES
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter()

RETRYABLE_BACKUP_STATUSES = {"failed", "cancelled"}


def _get_job_repository(
    db: Session, repository_path: Optional[str]
) -> Optional[Repository]:
    if not repository_path:
        return None
    return db.query(Repository).filter(Repository.path == repository_path).first()


def _get_backup_job_repository(db: Session, job: BackupJob) -> Optional[Repository]:
    if job.repository_id:
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo:
            return repo
    return _get_job_repository(db, job.repository)


def _resolve_backup_log_file(job: BackupJob):
    from pathlib import Path

    if getattr(job, "log_file_path", None):
        log_file = Path(job.log_file_path)
        if log_file.exists():
            return log_file

    if job.logs and job.logs.startswith("Logs saved to:"):
        log_filename = job.logs.replace("Logs saved to: ", "").strip()
        log_file = Path(settings.data_dir) / "logs" / log_filename
        if log_file.exists():
            return log_file

    return None


def _get_running_maintenance_job(
    db: Session,
    backup_job: BackupJob,
    maintenance_status: Optional[str],
):
    if maintenance_status == "running_prune":
        job_model = PruneJob
    elif maintenance_status == "running_compact":
        job_model = CompactJob
    elif maintenance_status == "running_check":
        job_model = CheckJob
    else:
        return None

    return (
        db.query(job_model)
        .filter(
            job_model.repository_path == backup_job.repository,
            job_model.status == "running",
        )
        .order_by(job_model.id.desc())
        .first()
    )


def _decode_json_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def _agent_job_logs_response(db: Session, backup_job: BackupJob, offset: int) -> dict:
    agent_job = get_agent_job_for_backup(db, backup_job)
    if not agent_job:
        return {
            "job_id": backup_job.id,
            "status": backup_job.status,
            "lines": [],
            "total_lines": 0,
            "has_more": False,
        }

    logs = (
        db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == agent_job.id)
        .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
        .all()
    )
    log_lines = [log.message for log in logs]
    lines_to_return = log_lines[offset:]
    return {
        "job_id": backup_job.id,
        "status": backup_job.status,
        "lines": [
            {"line_number": offset + i + 1, "content": line}
            for i, line in enumerate(lines_to_return)
        ],
        "total_lines": len(log_lines),
        "has_more": False,
    }


def _empty_backup_log_response(job: BackupJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "lines": [],
        "total_lines": 0,
        "has_more": False,
    }


def _get_agent_log_messages(db: Session, agent_job_id: int) -> list[str]:
    logs = (
        db.query(AgentJobLog)
        .filter(AgentJobLog.agent_job_id == agent_job_id)
        .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
        .all()
    )
    return [log.message for log in logs]


def _agent_log_rows_exist(db: Session, agent_job_id: int) -> bool:
    return (
        db.query(AgentJobLog.id)
        .filter(AgentJobLog.agent_job_id == agent_job_id)
        .first()
        is not None
    )


def _backup_job_has_logs(
    db: Session, job: Any, *, log_save_policy: str | None = None
) -> bool:
    return backup_job_has_logs(db, job, log_save_policy=log_save_policy)


def _get_backup_plan_name(db: Session, backup_plan_id: Optional[int]) -> Optional[str]:
    if not backup_plan_id:
        return None
    plan = db.query(BackupPlan).filter(BackupPlan.id == backup_plan_id).first()
    return plan.name if plan else None


def _retry_metadata(job: BackupJob) -> dict[str, Any]:
    return {
        "retry_attempt": job.retry_attempt or 1,
        "retry_original_job_id": job.retry_original_job_id,
        "retry_source_job_id": job.retry_source_job_id,
        "retry_requested_by_user_id": job.retry_requested_by_user_id,
        "retry_requested_at": serialize_datetime(job.retry_requested_at),
    }


def _backup_retry_response(job: BackupJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "message": "Backup job retry started",
        **_retry_metadata(job),
    }


def _ensure_backup_retry_supported(source_job: BackupJob) -> None:
    if source_job.status not in RETRYABLE_BACKUP_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.backup.retryOnlyTerminalFailedCancelled"},
        )
    if (
        source_job.scheduled_job_id is not None
        or source_job.backup_plan_id is not None
        or source_job.backup_plan_run_id is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.backup.retryUnsupportedJobType"},
        )
    if source_job.maintenance_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.backup.retryUnsupportedJobType"},
        )


def _backup_retry_request_snapshot(
    *,
    source_job: BackupJob,
    retry_job: BackupJob,
    repo: Repository,
) -> dict[str, Any]:
    source_directories = _decode_json_list(repo.source_directories)
    source_locations = _decode_json_list(repo.source_locations)
    exclude_patterns = _decode_json_list(repo.exclude_patterns)
    snapshot: dict[str, Any] = {
        "kind": "backup_job_retry",
        "source_job": {
            "id": source_job.id,
            "status": source_job.status,
            "execution_mode": source_job.execution_mode or "local",
            "archive_name": source_job.archive_name,
            "route_strategy": source_job.route_strategy,
        },
        "created_job": {
            "id": retry_job.id,
            "status": retry_job.status,
            "execution_mode": retry_job.execution_mode or "local",
            "route_strategy": retry_job.route_strategy,
        },
        "repository": {
            "id": repo.id,
            "path": repo.path,
            "executor_type": getattr(repo, "executor_type", None),
            "execution_target": getattr(repo, "execution_target", None),
            "borg_version": getattr(repo, "borg_version", 1),
        },
        "backup": {
            "execution_mode": retry_job.execution_mode or "local",
            "source_directories": source_directories,
            "source_locations": source_locations,
            "exclude_patterns": exclude_patterns,
            "compression": repo.compression or "lz4",
            "custom_flags": repo.custom_flags or "",
            "source_ssh_connection_id": retry_job.source_ssh_connection_id,
        },
    }
    return snapshot


async def _cancel_running_maintenance_job(db: Session, backup_job: BackupJob):
    failure_status = RUNNING_BACKUP_MAINTENANCE_FAILURES.get(
        backup_job.maintenance_status or ""
    )
    if not failure_status:
        return None

    maintenance_job = _get_running_maintenance_job(
        db, backup_job, backup_job.maintenance_status
    )
    backup_job.maintenance_status = failure_status

    if not maintenance_job:
        return SimpleNamespace(job=None, process_killed=False)

    repo = _get_job_repository(db, backup_job.repository)

    if failure_status == "prune_failed":
        if repo and getattr(repo, "borg_version", 1) == 2:
            from app.services.v2.prune_service import prune_v2_service

            process_killed = await prune_v2_service.cancel_prune(maintenance_job.id)
        else:
            from app.services.prune_service import prune_service

            process_killed = await prune_service.cancel_prune(maintenance_job.id)
    elif failure_status == "compact_failed":
        if repo and getattr(repo, "borg_version", 1) == 2:
            from app.services.v2.compact_service import compact_v2_service

            process_killed = await compact_v2_service.cancel_compact(maintenance_job.id)
        else:
            from app.services.compact_service import compact_service

            process_killed = await compact_service.cancel_compact(maintenance_job.id)
    elif failure_status == "check_failed":
        process_killed = False
    else:
        return None

    maintenance_job.status = "cancelled"
    maintenance_job.completed_at = datetime.utcnow()
    return SimpleNamespace(job=maintenance_job, process_killed=process_killed)


# Pydantic models
class BackupRequest(BaseModel):
    repository: str = None


class BackupResponse(BaseModel):
    job_id: int
    status: str
    message: str


async def _start_backup_impl(
    backup_request: BackupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a manual backup operation"""
    try:
        # Preserve legacy behavior for manual backups: the repository field is
        # optional, and unknown paths are accepted so the job can fail later in
        # the background worker rather than at request validation time.
        repo_record = None
        if backup_request.repository:
            repo_record = _get_job_repository(db, backup_request.repository)
            if repo_record is not None:
                check_repo_access(db, current_user, repo_record, "operator")
                if is_agent_executor(repo_record):
                    validate_agent_backup_repository(db, repo_record)

        ensure_manual_backup_capacity(db)
        if repo_record is not None:
            ensure_repository_admission(db, repo_record, OPERATION_BACKUP)

        if repo_record is None:
            # Legacy contract: an unknown or empty path is accepted and fails
            # at once, so polling clients get a terminal state. Created
            # uncommitted so the runner never sees it queued.
            backup_job = create_backup_operation(
                db,
                None,
                trigger="manual",
                executor="server",
                user_id=current_user.id,
                repository_path=backup_request.repository or "default",
                commit=False,
            )
            backup_job.status = "failed"
            backup_job.error_message = json.dumps(
                {"key": "backend.errors.borg.unknownError"}
            )
            backup_job.logs = (
                f"Repository record not found in database: {backup_request.repository}"
            )
            backup_job.completed_at = datetime.utcnow()
            db.commit()
        else:
            backup_job = create_backup_operation(
                db,
                repo_record,
                trigger="manual",
                executor="agent" if is_agent_executor(repo_record) else "server",
                user_id=current_user.id,
                repository_path=backup_request.repository or "default",
            )

        logger.info(
            "Backup job created", job_id=backup_job.id, user=current_user.username
        )

        return BackupResponse(
            job_id=backup_job.id, status="pending", message="Backup job started"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start backup: {str(e)}",
        )


@router.post("/start", response_model=BackupResponse)
async def start_backup(
    backup_request: BackupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a manual backup operation."""
    return await _start_backup_impl(backup_request, current_user, db)


@router.post("/run", response_model=BackupResponse)
async def run_backup(
    backup_request: BackupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compatibility alias for clients using /api/backup/run."""
    return await _start_backup_impl(backup_request, current_user, db)


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_backup_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retry a terminal manual backup job by creating a new job row."""
    source_job = resolve_backup_job(db, job_id)
    if not source_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.backup.backupJobNotFound"},
        )
    _ensure_backup_retry_supported(source_job)

    repo = _get_backup_job_repository(db, source_job)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"key": "backend.errors.backup.retryRequestNotReconstructable"},
        )
    check_repo_access(db, current_user, repo, "operator")

    ensure_manual_backup_capacity(db)
    attempt_number = (source_job.retry_attempt or 1) + 1
    original_job_id = source_job.retry_original_job_id or source_job.id
    requested_at = datetime.utcnow()
    agent = is_agent_executor(repo)
    if agent:
        validate_agent_backup_repository(db, repo)
    else:
        ensure_repository_admission(db, repo, OPERATION_BACKUP)

    retry_job = create_backup_operation(
        db,
        repo,
        trigger="retry",
        executor="agent" if agent else "server",
        user_id=current_user.id,
        retry={
            "retry_original_job_id": original_job_id,
            "retry_source_job_id": source_job.id,
            "retry_attempt": attempt_number,
            "retry_requested_by_user_id": current_user.id,
            "retry_requested_at": requested_at,
        },
        commit=False,
    )
    db.add(
        OperationBackupRetryLineage(
            original_job_id=original_job_id,
            retry_source_job_id=source_job.id,
            attempt_number=attempt_number,
            requested_by_user_id=current_user.id,
            requested_at=requested_at,
            created_operation_id=retry_job.id,
            request_snapshot=_backup_retry_request_snapshot(
                source_job=source_job,
                retry_job=retry_job,
                repo=repo,
            ),
        )
    )
    db.commit()
    wake_runner()
    logger.info(
        "Backup retry created",
        source_job_id=source_job.id,
        retry_job_id=retry_job.id,
        user=current_user.username,
    )
    return _backup_retry_response(retry_job)


@router.get("/jobs")
async def get_all_backup_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 200,
    scheduled_only: bool = False,
    manual_only: bool = False,
    repository: Optional[str] = None,
):
    """Get all backup jobs (most recent first) with progress details

    Args:
        scheduled_only: If True, only return jobs triggered by scheduled tasks
        manual_only: If True, only return manual backup jobs (not scheduled)
    """
    try:
        jobs = list_backup_jobs(
            db,
            limit,
            scheduled_only=scheduled_only,
            manual_only=manual_only,
            repository_path=repository,
        )
        visible_jobs = []
        for job in jobs:
            repo = _get_job_repository(db, job.repository)
            if repo is None:
                if current_user.role == "admin":
                    visible_jobs.append(job)
                continue
            try:
                check_repo_access(db, current_user, repo, "viewer")
                visible_jobs.append(job)
            except HTTPException:
                continue

        log_save_policy = get_log_save_policy(db)
        return {
            "jobs": [
                {
                    "id": job.id,
                    "repository": job.repository,
                    "status": job.status,
                    "started_at": serialize_datetime(job.started_at),
                    "completed_at": serialize_datetime(job.completed_at),
                    "progress": job.progress,
                    "error_message": job.error_message,
                    "has_logs": _backup_job_has_logs(
                        db, job, log_save_policy=log_save_policy
                    ),
                    "maintenance_status": job.maintenance_status,
                    "scheduled_job_id": job.scheduled_job_id,  # Include for filtering by schedule
                    "backup_plan_id": job.backup_plan_id,
                    "backup_plan_run_id": job.backup_plan_run_id,
                    "backup_plan_name": _get_backup_plan_name(db, job.backup_plan_id),
                    "triggered_by": (
                        "backup_plan"
                        if job.backup_plan_id
                        else "schedule"
                        if job.scheduled_job_id
                        else "manual"
                    ),
                    "archive_name": getattr(job, "archive_name", None),
                    "archive_pruned_at": serialize_datetime(job.archive_pruned_at),
                    "execution_mode": job.execution_mode or "local",
                    "route_strategy": job.route_strategy,
                    **_retry_metadata(job),
                    "progress_details": serialize_backup_progress_details(
                        job,
                        _get_job_repository(db, job.repository),
                    ),
                }
                for job in visible_jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get backup jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.backup.failedGetBackupJobs"},
        )


@router.get("/status/{job_id}")
async def get_backup_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get backup job status with detailed progress information"""
    try:
        job = resolve_backup_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"},
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "viewer")
        has_logs = _backup_job_has_logs(db, job)

        return {
            "id": job.id,
            "repository": job.repository,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "progress": job.progress,
            "error_message": job.error_message,
            "logs": job.logs if has_logs else None,
            "maintenance_status": job.maintenance_status,
            "backup_plan_id": job.backup_plan_id,
            "backup_plan_run_id": job.backup_plan_run_id,
            "backup_plan_name": _get_backup_plan_name(db, job.backup_plan_id),
            "execution_mode": job.execution_mode or "local",
            "triggered_by": (
                "backup_plan"
                if job.backup_plan_id
                else "schedule"
                if job.scheduled_job_id
                else "manual"
            ),
            **_retry_metadata(job),
            "progress_details": serialize_backup_progress_details(job, repo),
            "route_strategy": job.route_strategy,
        }
    except Exception as e:
        logger.error("Failed to get backup status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.backup.failedGetBackupStatus"},
        )


@router.post("/cancel/{job_id}")
async def cancel_backup(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a running backup job"""
    try:
        job = resolve_backup_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"},
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "operator")

        operation = is_backup_operation(job)
        if job.execution_mode == "agent":
            if operation:
                await operation_runner.request_cancel(job.id)
            cancel_agent_backup_job(db, job)
            process_killed = False
        elif job.status == "running":
            if operation:
                # Spec 7.7: the flag first, so the executor keeps `cancelled`
                # over the service's later `failed` write for the killed
                # process (the phase 7 restore pattern).
                await operation_runner.request_cancel(job.id)
            process_killed = await backup_service.cancel_backup(job_id)
            job.status = "cancelled"
            job.completed_at = datetime.utcnow()
            job.error_message = (
                CANCELLED_BY_USER if process_killed else CANCELLED_PROCESS_NOT_FOUND
            )
        elif operation and job.status == "pending":
            # A queued backup is new in this phase (it waits for the lane);
            # the runner marks it cancelled directly.
            await operation_runner.request_cancel(job.id)
            process_killed = False
        elif job.maintenance_status in RUNNING_BACKUP_MAINTENANCE_FAILURES:
            maintenance_result = await _cancel_running_maintenance_job(db, job)
            if maintenance_result is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"key": "backend.errors.backup.canOnlyCancelRunningJobs"},
                )
            process_killed = maintenance_result.process_killed
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.backup.canOnlyCancelRunningJobs"},
            )
        db.commit()

        logger.info(
            "Backup cancelled",
            job_id=job_id,
            user=current_user.username,
            process_killed=process_killed,
        )
        return {
            "message": "backend.success.backup.backupCancelled",
            "process_terminated": process_killed,
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to cancel backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.backup.failedCancelBackup"},
        )


@router.get("/logs/{job_id}/download")
async def download_backup_logs(
    job_id: int,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    """Download backup job logs as a file (only for failed/cancelled backups)"""
    try:
        from fastapi.responses import FileResponse

        job = resolve_backup_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"},
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "viewer")

        # Only allow download for completed failed/cancelled backups
        if job.status == "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "key": "backend.errors.backup.cannotDownloadLogsForRunningBackup"
                },
            )

        if not _backup_job_has_logs(db, job):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.noLogsAvailable"},
            )

        if job.execution_mode == "agent":
            agent_job = get_agent_job_for_backup(db, job)
            if not agent_job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"key": "backend.errors.backup.noLogsAvailable"},
                )
            logs = (
                db.query(AgentJobLog)
                .filter(AgentJobLog.agent_job_id == agent_job.id)
                .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
                .all()
            )
            if not logs:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"key": "backend.errors.backup.noLogsAvailable"},
                )

            import tempfile

            temp_file = tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            )
            temp_file.write("\n".join(log.message for log in logs))
            temp_file.close()
            return FileResponse(
                path=temp_file.name,
                filename=f"backup_job_{job_id}_logs.txt",
                media_type="text/plain",
            )

        # Check if logs are available
        if not job.logs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.noLogsAvailable"},
            )

        # Handle file-based logs
        if job.logs.startswith("Logs saved to:"):
            log_filename = job.logs.replace("Logs saved to: ", "").strip()
            log_file = _resolve_backup_log_file(job)

            if log_file is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "key": "backend.errors.backup.logFileNotFound",
                        "params": {"filename": log_filename},
                    },
                )

            # Return file as download
            return FileResponse(
                path=str(log_file),
                filename=f"backup_job_{job_id}_logs.txt",
                media_type="text/plain",
            )
        else:
            # Legacy: logs stored in database - create temp file
            import tempfile

            temp_file = tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            )
            temp_file.write(job.logs or "")
            temp_file.close()

            return FileResponse(
                path=temp_file.name,
                filename=f"backup_job_{job_id}_logs.txt",
                media_type="text/plain",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to download backup logs", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download logs: {str(e)}",
        )


@router.get("/logs/{job_id}/stream")
async def stream_backup_logs(
    job_id: int,
    offset: int = 0,  # Line number to start from
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get incremental backup logs (for real-time streaming)"""
    try:
        job = resolve_backup_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"},
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "viewer")

        if not _backup_job_has_logs(db, job):
            return _empty_backup_log_response(job)

        if job.execution_mode == "agent":
            return _agent_job_logs_response(db, job, offset)

        # Check if logs are available
        if not job.logs:
            # No logs (successful backup with performance optimization)
            return {
                "job_id": job.id,
                "status": job.status,
                "lines": [],
                "total_lines": 0,
                "has_more": False,
            }

        # Check if logs point to a file
        if job.logs.startswith("Logs saved to:"):
            # Parse file path from logs field
            log_filename = job.logs.replace("Logs saved to: ", "").strip()
            log_file = _resolve_backup_log_file(job)

            if log_file is not None:
                # Read log file and return lines
                try:
                    log_content = log_file.read_text()
                    log_lines = log_content.split("\n")

                    # Apply offset for streaming
                    lines_to_return = log_lines[offset:]
                    formatted_lines = [
                        {"line_number": offset + i + 1, "content": line}
                        for i, line in enumerate(lines_to_return)
                    ]

                    return {
                        "job_id": job.id,
                        "status": job.status,
                        "lines": formatted_lines,
                        "total_lines": len(log_lines),
                        "has_more": False,
                    }
                except Exception as e:
                    logger.error(
                        "Failed to read log file", log_file=str(log_file), error=str(e)
                    )
                    return {
                        "job_id": job.id,
                        "status": job.status,
                        "lines": [
                            {
                                "line_number": 1,
                                "content": f"Error reading log file: {str(e)}",
                            }
                        ],
                        "total_lines": 1,
                        "has_more": False,
                    }
            else:
                return {
                    "job_id": job.id,
                    "status": job.status,
                    "lines": [
                        {
                            "line_number": 1,
                            "content": f"Log file not found: {log_filename}",
                        }
                    ],
                    "total_lines": 1,
                    "has_more": False,
                }
        else:
            # Legacy: logs stored in database (shouldn't happen with new code)
            log_lines = job.logs.split("\n") if job.logs else []
            lines_to_return = log_lines[offset:]
            formatted_lines = [
                {"line_number": offset + i + 1, "content": line}
                for i, line in enumerate(lines_to_return)
            ]

            return {
                "job_id": job.id,
                "status": job.status,
                "lines": formatted_lines,
                "total_lines": len(log_lines),
                "has_more": False,
            }

    except Exception as e:
        logger.error("Failed to stream backup logs", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch logs: {str(e)}",
        )
