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
    """Get all backup jobs (most recent first)"""
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
                    "error_message": job.error_message
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
    """Get backup job status"""
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
            "logs": job.logs
        }
    except Exception as e:
        logger.error("Failed to get backup status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get backup status"
        )

@router.delete("/cancel/{job_id}")
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

@router.get("/logs/{job_id}")
async def get_backup_logs(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get backup job logs"""
    try:
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backup job not found"
            )

        return {
            "job_id": job.id,
            "logs": job.logs or "",
            "error_message": job.error_message or ""
        }
    except Exception as e:
        logger.error("Failed to get backup logs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get backup logs"
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

        # If no log file yet, return empty
        if not job.log_file_path or not os.path.exists(job.log_file_path):
            return {
                "job_id": job.id,
                "status": job.status,
                "lines": [],
                "total_lines": 0,
                "has_more": job.status == "running"
            }

        # Read log file from offset
        lines = []
        with open(job.log_file_path, 'r') as f:
            all_lines = f.readlines()
            total_lines = len(all_lines)

            # Get lines from offset onwards
            if offset < total_lines:
                lines = [{"line_number": offset + i + 1, "content": line.rstrip('\n')}
                         for i, line in enumerate(all_lines[offset:])]

        return {
            "job_id": job.id,
            "status": job.status,
            "lines": lines,
            "total_lines": total_lines,
            "has_more": job.status == "running"
        }

    except Exception as e:
        logger.error("Failed to stream backup logs", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch logs: {str(e)}"
        ) 