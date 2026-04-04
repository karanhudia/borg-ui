from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog
import asyncio
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import User, BackupJob, Repository
from app.config import settings
from app.core.security import (
    get_current_user,
    get_current_download_user,
    check_repo_access,
)
from app.services.backup_service import backup_service
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter()


def _get_job_repository(db: Session, repository_path: Optional[str]) -> Optional[Repository]:
    if not repository_path:
        return None
    return db.query(Repository).filter(Repository.path == repository_path).first()


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

# Pydantic models
class BackupRequest(BaseModel):
    repository: str = None

class BackupResponse(BaseModel):
    job_id: int
    status: str
    message: str

@router.post("/start", response_model=BackupResponse)
async def start_backup(
    backup_request: BackupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
                check_repo_access(db, current_user, repo_record, 'operator')

        # Create backup job record
        backup_job = BackupJob(
            repository=backup_request.repository or "default",
            status="pending",
            source_ssh_connection_id=repo_record.source_ssh_connection_id if repo_record else None
        )
        db.add(backup_job)
        db.commit()
        db.refresh(backup_job)

        # Execute backup asynchronously (non-blocking). Unknown repository paths are
        # still accepted for legacy compatibility, but are marked failed
        # immediately after job creation so polling clients get a deterministic
        # terminal state even in environments where background tasks may not run.
        if backup_request.repository and repo_record is None:
            backup_job.status = "failed"
            backup_job.error_message = json.dumps({"key": "backend.errors.borg.unknownError"})
            backup_job.logs = f"Repository record not found in database: {backup_request.repository}"
            backup_job.completed_at = datetime.utcnow()
            db.commit()
        else:
            asyncio.create_task(
                backup_service.execute_backup(
                    backup_job.id,
                    backup_request.repository,
                    None  # Create new session for background task
                )
            )

        logger.info("Backup job created", job_id=backup_job.id, user=current_user.username)

        return BackupResponse(
            job_id=backup_job.id,
            status="pending",
            message="Backup job started"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start backup: {str(e)}"
        )

@router.get("/jobs")
async def get_all_backup_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 200,
    scheduled_only: bool = False,
    manual_only: bool = False
):
    """Get all backup jobs (most recent first) with progress details

    Args:
        scheduled_only: If True, only return jobs triggered by scheduled tasks
        manual_only: If True, only return manual backup jobs (not scheduled)
    """
    try:
        query = db.query(BackupJob)

        if scheduled_only:
            # Filter to only jobs with scheduled_job_id set
            query = query.filter(BackupJob.scheduled_job_id.isnot(None))
        elif manual_only:
            # Filter to only jobs without scheduled_job_id (manual backups)
            query = query.filter(BackupJob.scheduled_job_id.is_(None))

        jobs = query.order_by(BackupJob.id.desc()).limit(limit).all()
        visible_jobs = []
        for job in jobs:
            repo = _get_job_repository(db, job.repository)
            if repo is None:
                if current_user.role == "admin":
                    visible_jobs.append(job)
                continue
            try:
                check_repo_access(db, current_user, repo, 'viewer')
                visible_jobs.append(job)
            except HTTPException:
                continue

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
                    "has_logs": bool(job.logs),  # Indicate if logs are available
                    "maintenance_status": job.maintenance_status,
                    "scheduled_job_id": job.scheduled_job_id,  # Include for filtering by schedule
                    "progress_details": {
                        "original_size": job.original_size or 0,
                        "compressed_size": job.compressed_size or 0,
                        "deduplicated_size": job.deduplicated_size or 0,
                        "nfiles": job.nfiles or 0,
                        "current_file": job.current_file or "",
                        "progress_percent": job.progress_percent or 0,
                        "backup_speed": job.backup_speed or 0.0,
                        "total_expected_size": job.total_expected_size or 0,
                        "estimated_time_remaining": job.estimated_time_remaining or 0
                    }
                }
                for job in visible_jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get backup jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.backup.failedGetBackupJobs"}
        )

@router.get("/status/{job_id}")
async def get_backup_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get backup job status with detailed progress information"""
    try:
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"}
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, 'viewer')

        return {
            "id": job.id,
            "repository": job.repository,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "progress": job.progress,
            "error_message": job.error_message,
            "logs": job.logs,
            "maintenance_status": job.maintenance_status,
            # Detailed progress from JSON parsing
            "progress_details": {
                "original_size": job.original_size or 0,
                "compressed_size": job.compressed_size or 0,
                "deduplicated_size": job.deduplicated_size or 0,
                "nfiles": job.nfiles or 0,
                "current_file": job.current_file or "",
                "progress_percent": job.progress_percent or 0,
                "backup_speed": job.backup_speed or 0.0,
                "total_expected_size": job.total_expected_size or 0,
                "estimated_time_remaining": job.estimated_time_remaining or 0
            }
        }
    except Exception as e:
        logger.error("Failed to get backup status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.backup.failedGetBackupStatus"}
        )

@router.post("/cancel/{job_id}")
async def cancel_backup(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a running backup job"""
    try:
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"}
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, 'operator')

        if job.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.backup.canOnlyCancelRunningJobs"}
            )

        # Try to terminate the actual process
        from app.services.backup_service import backup_service
        process_killed = await backup_service.cancel_backup(job_id)

        # Update job status in database
        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        if process_killed:
            job.error_message = '{"key": "backend.errors.backup.cancelledByUser"}'
        else:
            job.error_message = '{"key": "backend.errors.backup.cancelledByUserProcessNotFound"}'
        db.commit()

        logger.info("Backup cancelled", job_id=job_id, user=current_user.username, process_killed=process_killed)
        return {
            "message": "backend.success.backup.backupCancelled",
            "process_terminated": process_killed
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to cancel backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.backup.failedCancelBackup"}
        )

@router.get("/logs/{job_id}/download")
async def download_backup_logs(
    job_id: int,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db)
):
    """Download backup job logs as a file (only for failed/cancelled backups)"""
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path

        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"}
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, 'viewer')

        # Only allow download for completed failed/cancelled backups
        if job.status == "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.backup.cannotDownloadLogsForRunningBackup"}
            )

        # Check if logs are available
        if not job.logs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.noLogsAvailable"}
            )

        # Handle file-based logs
        if job.logs.startswith("Logs saved to:"):
            log_filename = job.logs.replace("Logs saved to: ", "").strip()
            log_file = _resolve_backup_log_file(job)

            if log_file is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"key": "backend.errors.backup.logFileNotFound", "params": {"filename": log_filename}}
                )

            # Return file as download
            return FileResponse(
                path=str(log_file),
                filename=f"backup_job_{job_id}_logs.txt",
                media_type="text/plain"
            )
        else:
            # Legacy: logs stored in database - create temp file
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
            temp_file.write(job.logs or "")
            temp_file.close()

            return FileResponse(
                path=temp_file.name,
                filename=f"backup_job_{job_id}_logs.txt",
                media_type="text/plain"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to download backup logs", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download logs: {str(e)}"
        )

@router.get("/logs/{job_id}/stream")
async def stream_backup_logs(
    job_id: int,
    offset: int = 0,  # Line number to start from
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get incremental backup logs (for real-time streaming)"""
    try:
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.backup.backupJobNotFound"}
            )
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, 'viewer')

        # Check if logs are available
        if not job.logs:
            # No logs (successful backup with performance optimization)
            return {
                "job_id": job.id,
                "status": job.status,
                "lines": [],
                "total_lines": 0,
                "has_more": False
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
                    log_lines = log_content.split('\n')

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
                        "has_more": False
                    }
                except Exception as e:
                    logger.error("Failed to read log file", log_file=str(log_file), error=str(e))
                    return {
                        "job_id": job.id,
                        "status": job.status,
                        "lines": [{"line_number": 1, "content": f"Error reading log file: {str(e)}"}],
                        "total_lines": 1,
                        "has_more": False
                    }
            else:
                return {
                    "job_id": job.id,
                    "status": job.status,
                    "lines": [{"line_number": 1, "content": f"Log file not found: {log_filename}"}],
                    "total_lines": 1,
                    "has_more": False
                }
        else:
            # Legacy: logs stored in database (shouldn't happen with new code)
            log_lines = job.logs.split('\n') if job.logs else []
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
                "has_more": False
            }

    except Exception as e:
        logger.error("Failed to stream backup logs", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch logs: {str(e)}"
        ) 
