from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog
import asyncio
import os
from typing import List, Dict, Any

from app.database.database import get_db
from app.database.models import User, BackupJob
from app.core.security import get_current_user
from app.services.backup_service import backup_service

logger = structlog.get_logger()
router = APIRouter()

# Pydantic models
class BackupRequest(BaseModel):
    repository: str = None
    config_file: str = None

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
                backup_request.config_file,
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
    limit: int = 50
):
    """Get all backup jobs (most recent first) with progress details"""
    try:
        jobs = db.query(BackupJob).order_by(BackupJob.id.desc()).limit(limit).all()

        return {
            "jobs": [
                {
                    "id": job.id,
                    "repository": job.repository,
                    "status": job.status,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "progress": job.progress,
                    "error_message": job.error_message,
                    "has_logs": bool(job.logs),  # Indicate if logs are available
                    "progress_details": {
                        "original_size": job.original_size or 0,
                        "compressed_size": job.compressed_size or 0,
                        "deduplicated_size": job.deduplicated_size or 0,
                        "nfiles": job.nfiles or 0,
                        "current_file": job.current_file or "",
                        "progress_percent": job.progress_percent or 0,
                        "backup_speed": job.backup_speed or 0.0
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
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "progress": job.progress,
            "error_message": job.error_message,
            "logs": job.logs,
            # Detailed progress from JSON parsing
            "progress_details": {
                "original_size": job.original_size or 0,
                "compressed_size": job.compressed_size or 0,
                "deduplicated_size": job.deduplicated_size or 0,
                "nfiles": job.nfiles or 0,
                "current_file": job.current_file or "",
                "progress_percent": job.progress_percent or 0,
                "backup_speed": job.backup_speed or 0.0
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
        
        job.status = "cancelled"
        db.commit()
        
        logger.info("Backup cancelled", job_id=job_id, user=current_user.username)
        return {"message": "Backup cancelled successfully"}
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