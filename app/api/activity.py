"""
Activity feed API endpoints.

Provides a unified view of all operations (backups, restores, checks, compacts, package installs).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from app.database.database import get_db
from app.database.models import BackupJob, RestoreJob, CheckJob, CompactJob, PackageInstallJob
from app.api.auth import get_current_user, User
from app.utils.datetime_utils import serialize_datetime

router = APIRouter(prefix="/api/activity", tags=["activity"])


class ActivityItem(BaseModel):
    id: int
    type: str  # 'backup', 'restore', 'check', 'compact', 'package'
    status: str  # 'pending', 'running', 'completed', 'failed'
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    repository: Optional[str]  # Repository path/name (if applicable)
    log_file_path: Optional[str]  # Path to streaming log file

    # Type-specific metadata
    archive_name: Optional[str] = None  # For backup/restore
    package_name: Optional[str] = None  # For package installs

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
            activities.append({
                'id': job.id,
                'type': 'backup',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': job.repository,
                'log_file_path': job.log_file_path,
                'archive_name': None,
                'package_name': None
            })

    # Fetch restore jobs
    if not job_type or job_type == 'restore':
        restore_jobs = db.query(RestoreJob).order_by(RestoreJob.started_at.desc()).limit(limit).all()
        for job in restore_jobs:
            if status and job.status != status:
                continue
            activities.append({
                'id': job.id,
                'type': 'restore',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': job.repository,
                'log_file_path': getattr(job, 'log_file_path', None),
                'archive_name': job.archive,
                'package_name': None
            })

    # Fetch check jobs
    if not job_type or job_type == 'check':
        check_jobs = db.query(CheckJob).order_by(CheckJob.started_at.desc()).limit(limit).all()
        for job in check_jobs:
            if status and job.status != status:
                continue
            activities.append({
                'id': job.id,
                'type': 'check',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': job.repository_path,
                'log_file_path': job.log_file_path,
                'archive_name': None,
                'package_name': None
            })

    # Fetch compact jobs
    if not job_type or job_type == 'compact':
        compact_jobs = db.query(CompactJob).order_by(CompactJob.started_at.desc()).limit(limit).all()
        for job in compact_jobs:
            if status and job.status != status:
                continue
            activities.append({
                'id': job.id,
                'type': 'compact',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': job.repository_path,
                'log_file_path': job.log_file_path,
                'archive_name': None,
                'package_name': None
            })

    # Fetch package install jobs
    if not job_type or job_type == 'package':
        package_jobs = db.query(PackageInstallJob).order_by(PackageInstallJob.started_at.desc()).limit(limit).all()
        for job in package_jobs:
            if status and job.status != status:
                continue
            activities.append({
                'id': job.id,
                'type': 'package',
                'status': job.status,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'repository': None,
                'log_file_path': job.log_file_path,
                'archive_name': None,
                'package_name': job.package_name
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get logs for a specific job.

    Supports streaming logs from file (for running jobs) or returning stored logs.
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

    # If job is completed/failed and has stored logs, return them
    if job.status in ['completed', 'failed'] and job.logs:
        lines = job.logs.split('\n')
        total_lines = len(lines)

        # Apply offset and return chunk
        chunk_size = 100
        end_offset = min(offset + chunk_size, total_lines)
        chunk = lines[offset:end_offset]

        return {
            'lines': [{'line_number': offset + i + 1, 'content': line} for i, line in enumerate(chunk)],
            'total_lines': total_lines,
            'has_more': end_offset < total_lines
        }

    # If job is running and has log file, stream from file
    if job.log_file_path and os.path.exists(job.log_file_path):
        try:
            with open(job.log_file_path, 'r') as f:
                lines = f.readlines()
                total_lines = len(lines)

                chunk_size = 100
                end_offset = min(offset + chunk_size, total_lines)
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


import os
