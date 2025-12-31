from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog
import asyncio
import os
from typing import List, Dict, Any
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import User, BackupJob
from app.core.security import get_current_user
from app.services.backup_service import backup_service
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter()

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
        # Create backup job record
        backup_job = BackupJob(
            repository=backup_request.repository or "default",
            status="pending"
        )
        db.add(backup_job)
        db.commit()
        db.refresh(backup_job)

        # Execute backup asynchronously (non-blocking)
        asyncio.create_task(
            backup_service.execute_backup(
                backup_job.id,
                backup_request.repository,
                db
            )
        )

        logger.info("Backup job created", job_id=backup_job.id, user=current_user.username)

        return BackupResponse(
            job_id=backup_job.id,
            status="pending",
            message="Backup job started"
        )
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
    limit: int = 50,
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
                for job in jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get backup jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get backup jobs"
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
                detail="Backup job not found"
            )

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
            detail="Failed to get backup status"
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
                detail="Backup job not found"
            )

        if job.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only cancel running jobs"
            )

        # Try to terminate the actual process
        from app.services.backup_service import backup_service
        process_killed = await backup_service.cancel_backup(job_id)

        # Update job status in database
        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        if process_killed:
            job.error_message = "Backup cancelled by user"
        else:
            job.error_message = "Backup cancelled by user (process not found, may have already completed)"
        db.commit()

        logger.info("Backup cancelled", job_id=job_id, user=current_user.username, process_killed=process_killed)
        return {
            "message": "Backup cancelled successfully",
            "process_terminated": process_killed
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to cancel backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel backup"
        )

@router.get("/logs/{job_id}/download")
async def download_backup_logs(
    job_id: int,
    token: str = None,
    db: Session = Depends(get_db)
):
    """Download backup job logs as a file (only for failed/cancelled backups)"""
    # Handle authentication from query parameter (for download links)
    from app.core.security import verify_token
    from app.database.models import User as UserModel

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required"
        )

    try:
        username = verify_token(token)
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        # Get user from database
        current_user = db.query(UserModel).filter(UserModel.username == username).first()
        if not current_user or not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication"
        )
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path

        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backup job not found"
            )

        # Only allow download for completed failed/cancelled backups
        if job.status == "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot download logs for running backup"
            )

        # Check if logs are available
        if not job.logs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No logs available for this backup (successful backups don't save logs)"
            )

        # Handle file-based logs
        if job.logs.startswith("Logs saved to:"):
            log_filename = job.logs.replace("Logs saved to: ", "").strip()
            log_file = Path("/data/logs") / log_filename

            if not log_file.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Log file not found: {log_filename}"
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
                detail="Backup job not found"
            )

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
            from pathlib import Path
            log_filename = job.logs.replace("Logs saved to: ", "").strip()
            log_file = Path("/data/logs") / log_filename

            if log_file.exists():
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