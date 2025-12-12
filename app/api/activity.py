"""
Activity feed API endpoints.

Provides a unified view of all operations (backups, restores, checks, compacts, package installs).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from pathlib import Path
import os
import structlog
import tempfile

from app.database.database import get_db
from app.database.models import BackupJob, RestoreJob, CheckJob, CompactJob, PackageInstallJob, Repository, InstalledPackage
from app.api.auth import get_current_user, User
from app.utils.datetime_utils import serialize_datetime
from app.services.backup_service import backup_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/activity", tags=["activity"])


class ActivityItem(BaseModel):
    id: int
    type: str  # 'backup', 'restore', 'check', 'compact', 'package'
    status: str  # 'pending', 'running', 'completed', 'failed', 'completed_with_warnings'
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    repository: Optional[str]  # Repository path/name (if applicable)
    log_file_path: Optional[str]  # Path to streaming log file
    triggered_by: str = 'manual'  # 'manual' or 'schedule'
    schedule_id: Optional[int] = None  # ScheduledJob ID if triggered_by schedule

    # Type-specific metadata
    archive_name: Optional[str] = None  # For backup/restore
    package_name: Optional[str] = None  # For package installs
    has_logs: bool = False  # Whether logs are available for download
    repository_path: Optional[str] = None  # Full repository path (for mapping to friendly name)

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: serialize_datetime(v)
        }


@router.get("/recent", response_model=List[ActivityItem])
async def list_recent_activity(
    limit: int = 50,
    job_type: Optional[str] = None,  # Filter by type: 'backup', 'restore', etc.
    status: Optional[str] = None,  # Filter by status: 'running', 'completed', 'failed'
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get recent activity across all job types.

    Returns a unified list of all operations sorted by start time (most recent first).
    Excludes the logs column for performance - use the logs endpoint to fetch logs.
    """

    activities = []

    # Fetch backup jobs
    if not job_type or job_type == 'backup':
        backup_jobs = db.query(BackupJob).order_by(BackupJob.started_at.desc()).limit(limit).all()
        for job in backup_jobs:
            if status and job.status != status:
                continue
            # Get repository name from path
            repo = db.query(Repository).filter(Repository.path == job.repository).first()
            repo_name = repo.name if repo else job.repository

            # Determine trigger type
            triggered_by = 'schedule' if job.scheduled_job_id else 'manual'

            activities.append({
                'id': job.id,
                'type': 'backup',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': repo_name,
                'repository_path': job.repository,  # Always include the path
                'log_file_path': job.log_file_path,
                'triggered_by': triggered_by,
                'schedule_id': job.scheduled_job_id,
                'archive_name': None,
                'package_name': None,
                'has_logs': bool(job.log_file_path or job.logs)
            })

    # Fetch restore jobs
    if not job_type or job_type == 'restore':
        restore_jobs = db.query(RestoreJob).order_by(RestoreJob.started_at.desc()).limit(limit).all()
        for job in restore_jobs:
            if status and job.status != status:
                continue
            # Get repository name from path
            repo = db.query(Repository).filter(Repository.path == job.repository).first()
            repo_name = repo.name if repo else job.repository

            activities.append({
                'id': job.id,
                'type': 'restore',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': repo_name,
                'repository_path': job.repository,  # Always include the path
                'log_file_path': getattr(job, 'log_file_path', None),
                'triggered_by': 'manual',  # Restore jobs are always manual
                'schedule_id': None,
                'archive_name': job.archive,
                'package_name': None,
                'has_logs': bool(getattr(job, 'log_file_path', None))
            })

    # Fetch check jobs
    if not job_type or job_type == 'check':
        check_jobs = db.query(CheckJob).order_by(CheckJob.started_at.desc()).limit(limit).all()
        for job in check_jobs:
            if status and job.status != status:
                continue
            # Get repository name from repository_id
            repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
            repo_name = repo.name if repo else None
            repo_path = repo.path if repo else None

            activities.append({
                'id': job.id,
                'type': 'check',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': repo_name,
                'repository_path': repo_path,
                'log_file_path': getattr(job, 'log_file_path', None),
                'triggered_by': 'manual',  # Check jobs are always manual
                'schedule_id': None,
                'archive_name': None,
                'package_name': None,
                'has_logs': bool(getattr(job, 'log_file_path', None))
            })

    # Fetch compact jobs
    if not job_type or job_type == 'compact':
        compact_jobs = db.query(CompactJob).order_by(CompactJob.started_at.desc()).limit(limit).all()
        for job in compact_jobs:
            if status and job.status != status:
                continue
            # Get repository name from repository_id
            repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
            repo_name = repo.name if repo else None
            repo_path = repo.path if repo else None

            activities.append({
                'id': job.id,
                'type': 'compact',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': repo_name,
                'repository_path': repo_path,
                'log_file_path': getattr(job, 'log_file_path', None),
                'triggered_by': 'manual',  # Compact jobs are always manual
                'schedule_id': None,
                'archive_name': None,
                'package_name': None,
                'has_logs': bool(getattr(job, 'log_file_path', None))
            })

    # Fetch package install jobs
    if not job_type or job_type == 'package':
        package_jobs = db.query(PackageInstallJob).order_by(PackageInstallJob.started_at.desc()).limit(limit).all()
        for job in package_jobs:
            if status and job.status != status:
                continue
            # Get package name from package_id
            package = db.query(InstalledPackage).filter(InstalledPackage.id == job.package_id).first()
            package_name = package.name if package else f"Package #{job.package_id}"

            activities.append({
                'id': job.id,
                'type': 'package',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': None,
                'log_file_path': getattr(job, 'log_file_path', None),
                'triggered_by': 'manual',  # Package jobs are always manual
                'schedule_id': None,
                'archive_name': None,
                'package_name': package_name,
                'has_logs': bool(getattr(job, 'log_file_path', None))
            })

    # Sort by started_at (most recent first)
    activities.sort(key=lambda x: x['started_at'] if x['started_at'] else datetime.min, reverse=True)

    # Apply limit to combined results
    activities = activities[:limit]

    return activities


@router.get("/{job_type}/{job_id}/logs")
async def get_job_logs(
    job_type: str,
    job_id: int,
    offset: int = 0,
    limit: int = 500,  # Default to 500 lines per request
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get logs for a specific job.

    Supports streaming logs from file (for running jobs) or returning stored logs.
    Returns max 500 lines per request to prevent performance issues.
    """

    # Map job type to model
    job_models = {
        'backup': BackupJob,
        'restore': RestoreJob,
        'check': CheckJob,
        'compact': CompactJob,
        'package': PackageInstallJob
    }

    if job_type not in job_models:
        raise HTTPException(status_code=400, detail=f"Invalid job type: {job_type}")

    job_model = job_models[job_type]
    job = db.query(job_model).filter(job_model.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail=f"{job_type.capitalize()} job not found")

    # For completed/failed jobs, prefer log_file_path (full borg output) over logs (hooks only)
    if job.status in ['completed', 'failed']:
        # First try reading from log file (contains all borg output)
        log_file_path = getattr(job, 'log_file_path', None)
        if log_file_path and os.path.exists(log_file_path):
            try:
                with open(log_file_path, 'r') as f:
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
                        'lines': [{'line_number': offset + i + 1, 'content': line} for i, line in enumerate(chunk)],
                        'total_lines': total_lines,
                        'has_more': end_offset < total_lines
                    }
            except Exception as e:
                # If file read fails, fall through to stored logs
                logger.warning("Failed to read log file, falling back to stored logs",
                             job_type=job_type, job_id=job_id, error=str(e))

        # Fallback to stored logs in database (hooks or error messages)
        if job.logs:
            lines = job.logs.split('\n')
            total_lines = len(lines)

            # Apply offset and limit
            end_offset = min(offset + limit, total_lines)
            chunk = lines[offset:end_offset]

            return {
                'lines': [{'line_number': offset + i + 1, 'content': line} for i, line in enumerate(chunk)],
                'total_lines': total_lines,
                'has_more': end_offset < total_lines
            }

    # For running jobs without log files (backup, check, compact), show progress message
    if job.status == 'running':
        if job_type == 'backup':
            # For running backups, try to get log buffer (last 500 lines)
            log_buffer = backup_service.get_log_buffer(job_id, tail_lines=500)

            if log_buffer:
                # Return last 500 lines from in-memory buffer
                return {
                    'lines': [{'line_number': i + 1, 'content': line} for i, line in enumerate(log_buffer)],
                    'total_lines': len(log_buffer),
                    'has_more': False  # Always show tail for running jobs
                }
            else:
                # No buffer yet (job just started)
                lines = [
                    "Backup is currently running...",
                    "",
                    "Waiting for logs...",
                    "",
                    "Note: Showing last 500 lines from in-memory buffer. Full logs not saved to disk."
                ]
        elif job_type in ['check', 'compact']:
            # Check/compact show progress message
            progress_msg = getattr(job, 'progress_message', None)
            if progress_msg:
                lines = [
                    f"Job is currently running...",
                    f"",
                    f"Current progress: {progress_msg}",
                    f"",
                    f"Full logs will be available after the job completes."
                ]
            else:
                lines = [
                    f"Job is currently running...",
                    f"",
                    f"Full logs will be available after the job completes."
                ]
        else:
            lines = ["Job is currently running..."]

        return {
            'lines': [{'line_number': i + 1, 'content': line} for i, line in enumerate(lines)],
            'total_lines': len(lines),
            'has_more': False
        }

    # If job is running and has log file, stream from file
    log_file_path = getattr(job, 'log_file_path', None)
    if log_file_path and os.path.exists(log_file_path):
        try:
            with open(log_file_path, 'r') as f:
                lines = f.readlines()
                total_lines = len(lines)

                # For running jobs, if offset is 0, get last 500 lines + new ones
                # This prevents loading huge log files into memory
                if offset == 0 and total_lines > limit:
                    start_offset = total_lines - limit
                    chunk = lines[start_offset:]
                    return {
                        'lines': [{'line_number': start_offset + i + 1, 'content': line.rstrip()} for i, line in enumerate(chunk)],
                        'total_lines': total_lines,
                        'has_more': False  # For running jobs, we only show tail
                    }

                # Normal pagination
                end_offset = min(offset + limit, total_lines)
                chunk = lines[offset:end_offset]

                return {
                    'lines': [{'line_number': offset + i + 1, 'content': line.rstrip()} for i, line in enumerate(chunk)],
                    'total_lines': total_lines,
                    'has_more': end_offset < total_lines
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read log file: {str(e)}")

    # No logs available
    return {
        'lines': [],
        'total_lines': 0,
        'has_more': False
    }


@router.get("/{job_type}/{job_id}/logs/download")
async def download_job_logs(
    job_type: str,
    job_id: int,
    token: str = None,
    db: Session = Depends(get_db)
):
    """Download logs for a specific job as a file."""
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
    except Exception as e:
        logger.error("Failed to verify token for log download", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

    # Map job type to model
    job_models = {
        'backup': BackupJob,
        'restore': RestoreJob,
        'check': CheckJob,
        'compact': CompactJob,
        'package': PackageInstallJob
    }

    if job_type not in job_models:
        raise HTTPException(status_code=400, detail=f"Invalid job type: {job_type}")

    job_model = job_models[job_type]
    job = db.query(job_model).filter(job_model.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail=f"{job_type.capitalize()} job not found")

    # Don't allow downloading logs for running jobs
    if job.status == 'running':
        raise HTTPException(
            status_code=400,
            detail="Cannot download logs for running job"
        )

    # Try to get logs from log file first
    log_file_path = getattr(job, 'log_file_path', None)
    if log_file_path and os.path.exists(log_file_path):
        return FileResponse(
            path=log_file_path,
            filename=f"{job_type}_job_{job_id}_logs.txt",
            media_type="text/plain"
        )

    # Fallback to database logs
    if hasattr(job, 'logs') and job.logs:
        # Create temp file with logs
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        try:
            temp_file.write(job.logs)
            temp_file.flush()
            temp_file.close()

            return FileResponse(
                path=temp_file.name,
                filename=f"{job_type}_job_{job_id}_logs.txt",
                media_type="text/plain"
            )
        except Exception as e:
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise e

    # No logs available
    raise HTTPException(
        status_code=404,
        detail="No logs available for this job"
    )
