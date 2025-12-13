from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import structlog
import croniter
import json
import os
import asyncio

from app.database.database import get_db
from app.database.models import User, ScheduledJob, CompactJob, PruneJob, Repository, BackupJob
from app.core.security import get_current_user
from app.core.borg import BorgInterface
from app.config import settings
from app.services.notification_service import notification_service
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(tags=["schedule"])

# Initialize Borg interface
borg = BorgInterface()

# Pydantic models
from pydantic import BaseModel

class ScheduledJobCreate(BaseModel):
    name: str
    cron_expression: str
    repository: Optional[str] = None
    enabled: bool = True
    description: Optional[str] = None
    archive_name_template: Optional[str] = None  # Template for archive names (e.g., "{job_name}-{now}")
    # Prune and compact settings
    run_prune_after: bool = False
    run_compact_after: bool = False
    prune_keep_hourly: int = 0
    prune_keep_daily: int = 7
    prune_keep_weekly: int = 4
    prune_keep_monthly: int = 6
    prune_keep_quarterly: int = 0
    prune_keep_yearly: int = 1

class ScheduledJobUpdate(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    repository: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    archive_name_template: Optional[str] = None  # Template for archive names (e.g., "{job_name}-{now}")
    # Prune and compact settings
    run_prune_after: Optional[bool] = None
    run_compact_after: Optional[bool] = None
    prune_keep_hourly: Optional[int] = None
    prune_keep_daily: Optional[int] = None
    prune_keep_weekly: Optional[int] = None
    prune_keep_monthly: Optional[int] = None
    prune_keep_quarterly: Optional[int] = None
    prune_keep_yearly: Optional[int] = None

class CronExpression(BaseModel):
    minute: str = "*"
    hour: str = "*"
    day_of_month: str = "*"
    month: str = "*"
    day_of_week: str = "*"

@router.get("/")
async def get_scheduled_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all scheduled jobs"""
    try:
        jobs = db.query(ScheduledJob).all()
        return {
            "success": True,
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "cron_expression": job.cron_expression,
                    "repository": job.repository,
                    "enabled": job.enabled,
                    "last_run": serialize_datetime(job.last_run),
                    "next_run": serialize_datetime(job.next_run),
                    "created_at": serialize_datetime(job.created_at),
                    "updated_at": serialize_datetime(job.updated_at),
                    "description": job.description,
                    "archive_name_template": job.archive_name_template,
                    # Prune and compact settings
                    "run_prune_after": job.run_prune_after,
                    "run_compact_after": job.run_compact_after,
                    "prune_keep_hourly": job.prune_keep_hourly,
                    "prune_keep_daily": job.prune_keep_daily,
                    "prune_keep_weekly": job.prune_keep_weekly,
                    "prune_keep_monthly": job.prune_keep_monthly,
                    "prune_keep_quarterly": job.prune_keep_quarterly,
                    "prune_keep_yearly": job.prune_keep_yearly,
                    "last_prune": serialize_datetime(job.last_prune),
                    "last_compact": serialize_datetime(job.last_compact),
                }
                for job in jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get scheduled jobs", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve scheduled jobs: {str(e)}")

@router.post("/")
async def create_scheduled_job(
    job_data: ScheduledJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new scheduled job"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Validate cron expression
        try:
            cron = croniter.croniter(job_data.cron_expression, datetime.now(timezone.utc))
            next_run = cron.get_next(datetime)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid cron expression: {str(e)}")
        
        # Check if job name already exists
        existing_job = db.query(ScheduledJob).filter(ScheduledJob.name == job_data.name).first()
        if existing_job:
            raise HTTPException(status_code=400, detail="Job name already exists")

        # Validate repository is not in observability-only mode
        if job_data.repository:
            from app.database.models import Repository
            repo = db.query(Repository).filter(Repository.path == job_data.repository).first()
            if repo and repo.mode == "observe":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot schedule backups for observability-only repositories. This repository is configured for browsing and restoring existing archives only."
                )

        # Create scheduled job
        scheduled_job = ScheduledJob(
            name=job_data.name,
            cron_expression=job_data.cron_expression,
            repository=job_data.repository,
            enabled=job_data.enabled,
            next_run=next_run,
            description=job_data.description,
            archive_name_template=job_data.archive_name_template,
            # Prune and compact settings
            run_prune_after=job_data.run_prune_after,
            run_compact_after=job_data.run_compact_after,
            prune_keep_hourly=job_data.prune_keep_hourly,
            prune_keep_daily=job_data.prune_keep_daily,
            prune_keep_weekly=job_data.prune_keep_weekly,
            prune_keep_monthly=job_data.prune_keep_monthly,
            prune_keep_quarterly=job_data.prune_keep_quarterly,
            prune_keep_yearly=job_data.prune_keep_yearly
        )
        
        db.add(scheduled_job)
        db.commit()
        db.refresh(scheduled_job)
        
        logger.info("Scheduled job created", name=job_data.name, user=current_user.username)
        
        return {
            "success": True,
            "message": "Scheduled job created successfully",
            "job": {
                "id": scheduled_job.id,
                "name": scheduled_job.name,
                "cron_expression": scheduled_job.cron_expression,
                "repository": scheduled_job.repository,
                "enabled": scheduled_job.enabled,
                "next_run": serialize_datetime(scheduled_job.next_run)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create scheduled job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create scheduled job: {str(e)}")

@router.get("/cron-presets")
async def get_cron_presets(current_user: User = Depends(get_current_user)):
    """Get common cron expression presets"""
    presets = [
        {
            "name": "Every Minute",
            "expression": "* * * * *",
            "description": "Run every minute"
        },
        {
            "name": "Every 5 Minutes",
            "expression": "*/5 * * * *",
            "description": "Run every 5 minutes"
        },
        {
            "name": "Every 15 Minutes",
            "expression": "*/15 * * * *",
            "description": "Run every 15 minutes"
        },
        {
            "name": "Every Hour",
            "expression": "0 * * * *",
            "description": "Run every hour"
        },
        {
            "name": "Every 6 Hours",
            "expression": "0 */6 * * *",
            "description": "Run every 6 hours"
        },
        {
            "name": "Daily at Midnight",
            "expression": "0 0 * * *",
            "description": "Run daily at midnight"
        },
        {
            "name": "Daily at 2 AM",
            "expression": "0 2 * * *",
            "description": "Run daily at 2 AM"
        },
        {
            "name": "Weekly on Sunday",
            "expression": "0 0 * * 0",
            "description": "Run weekly on Sunday at midnight"
        },
        {
            "name": "Monthly on 1st",
            "expression": "0 0 1 * *",
            "description": "Run monthly on the 1st at midnight"
        },
        {
            "name": "Weekdays at 9 AM",
            "expression": "0 9 * * 1-5",
            "description": "Run weekdays at 9 AM"
        },
        {
            "name": "Weekends at 6 AM",
            "expression": "0 6 * * 0,6",
            "description": "Run weekends at 6 AM"
        }
    ]
    
    return {
        "success": True,
        "presets": presets
    }

@router.get("/upcoming-jobs")
async def get_upcoming_jobs(
    hours: int = Query(24, description="Hours to look ahead"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get upcoming scheduled jobs"""
    try:
        jobs = db.query(ScheduledJob).filter(ScheduledJob.enabled == True).all()
        upcoming_jobs = []

        end_time = datetime.now(timezone.utc) + timedelta(hours=hours)

        for job in jobs:
            try:
                cron = croniter.croniter(job.cron_expression, datetime.now(timezone.utc))
                next_run = cron.get_next(datetime)
                
                if next_run <= end_time:
                    upcoming_jobs.append({
                        "id": job.id,
                        "name": job.name,
                        "repository": job.repository,
                        "next_run": serialize_datetime(next_run),
                        "cron_expression": job.cron_expression
                    })
            except:
                continue
        
        # Sort by next run time
        upcoming_jobs.sort(key=lambda x: x["next_run"])
        
        return {
            "success": True,
            "upcoming_jobs": upcoming_jobs,
            "hours_ahead": hours
        }
    except Exception as e:
        logger.error("Failed to get upcoming jobs", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get upcoming jobs: {str(e)}")

@router.get("/{job_id}")
async def get_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get scheduled job details"""
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        
        # Calculate next run times
        try:
            cron = croniter.croniter(job.cron_expression, datetime.now(timezone.utc))
            next_runs = []
            for i in range(5):  # Get next 5 run times
                next_dt = cron.get_next(datetime)
                next_runs.append(serialize_datetime(next_dt))
        except:
            next_runs = []

        return {
            "success": True,
            "job": {
                "id": job.id,
                "name": job.name,
                "cron_expression": job.cron_expression,
                "repository": job.repository,
                "enabled": job.enabled,
                "last_run": serialize_datetime(job.last_run),
                "next_run": serialize_datetime(job.next_run),
                "next_runs": next_runs,
                "created_at": serialize_datetime(job.created_at),
                "updated_at": serialize_datetime(job.updated_at),
                "description": job.description,
                "archive_name_template": job.archive_name_template,
                # Prune and compact settings
                "run_prune_after": job.run_prune_after,
                "run_compact_after": job.run_compact_after,
                "prune_keep_hourly": job.prune_keep_hourly,
                "prune_keep_daily": job.prune_keep_daily,
                "prune_keep_weekly": job.prune_keep_weekly,
                "prune_keep_monthly": job.prune_keep_monthly,
                "prune_keep_quarterly": job.prune_keep_quarterly,
                "prune_keep_yearly": job.prune_keep_yearly,
                "last_prune": serialize_datetime(job.last_prune),
                "last_compact": serialize_datetime(job.last_compact),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get scheduled job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve scheduled job: {str(e)}")

@router.put("/{job_id}")
async def update_scheduled_job(
    job_id: int,
    job_data: ScheduledJobUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update scheduled job"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        
        # Update fields
        if job_data.name is not None:
            # Check if name already exists
            existing_job = db.query(ScheduledJob).filter(
                ScheduledJob.name == job_data.name,
                ScheduledJob.id != job_id
            ).first()
            if existing_job:
                raise HTTPException(status_code=400, detail="Job name already exists")
            job.name = job_data.name
        
        if job_data.cron_expression is not None:
            # Validate cron expression
            try:
                cron = croniter.croniter(job_data.cron_expression, datetime.now(timezone.utc))
                job.cron_expression = job_data.cron_expression
                job.next_run = cron.get_next(datetime)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid cron expression: {str(e)}")
        
        if job_data.repository is not None:
            # Validate repository is not in observability-only mode
            from app.database.models import Repository
            repo = db.query(Repository).filter(Repository.path == job_data.repository).first()
            if repo and repo.mode == "observe":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot schedule backups for observability-only repositories. This repository is configured for browsing and restoring existing archives only."
                )
            job.repository = job_data.repository

        if job_data.enabled is not None:
            job.enabled = job_data.enabled
        
        if job_data.description is not None:
            job.description = job_data.description

        if job_data.archive_name_template is not None:
            job.archive_name_template = job_data.archive_name_template

        # Update prune and compact settings
        if job_data.run_prune_after is not None:
            job.run_prune_after = job_data.run_prune_after

        if job_data.run_compact_after is not None:
            job.run_compact_after = job_data.run_compact_after

        if job_data.prune_keep_hourly is not None:
            job.prune_keep_hourly = job_data.prune_keep_hourly

        if job_data.prune_keep_daily is not None:
            job.prune_keep_daily = job_data.prune_keep_daily

        if job_data.prune_keep_weekly is not None:
            job.prune_keep_weekly = job_data.prune_keep_weekly

        if job_data.prune_keep_monthly is not None:
            job.prune_keep_monthly = job_data.prune_keep_monthly

        if job_data.prune_keep_quarterly is not None:
            job.prune_keep_quarterly = job_data.prune_keep_quarterly

        if job_data.prune_keep_yearly is not None:
            job.prune_keep_yearly = job_data.prune_keep_yearly

        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info("Scheduled job updated", job_id=job_id, user=current_user.username)
        
        return {
            "success": True,
            "message": "Scheduled job updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update scheduled job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update scheduled job: {str(e)}")

@router.delete("/{job_id}")
async def delete_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete scheduled job (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        
        db.delete(job)
        db.commit()
        
        logger.info("Scheduled job deleted", job_id=job_id, user=current_user.username)
        
        return {
            "success": True,
            "message": "Scheduled job deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete scheduled job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete scheduled job: {str(e)}")

@router.post("/{job_id}/toggle")
async def toggle_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle scheduled job enabled/disabled state"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        
        job.enabled = not job.enabled
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info("Scheduled job toggled", job_id=job_id, enabled=job.enabled, user=current_user.username)
        
        return {
            "success": True,
            "message": f"Scheduled job {'enabled' if job.enabled else 'disabled'} successfully",
            "enabled": job.enabled
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to toggle scheduled job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to toggle scheduled job: {str(e)}")

@router.post("/{job_id}/run-now")
async def run_scheduled_job_now(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Run a scheduled job immediately"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from app.database.models import BackupJob, Repository
        from app.services.backup_service import backup_service

        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Scheduled job not found")

        # Get repository info
        repo = db.query(Repository).filter(Repository.path == job.repository).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found for scheduled job")

        # Create backup job record with scheduled_job_id
        backup_job = BackupJob(
            repository=job.repository or "default",
            status="pending",
            scheduled_job_id=job.id  # Link to scheduled job
        )
        db.add(backup_job)
        db.commit()
        db.refresh(backup_job)

        # Generate archive name from template
        archive_name = None
        if job.archive_name_template:
            # Replace template placeholders
            archive_name = job.archive_name_template
            archive_name = archive_name.replace("{job_name}", job.name)
            archive_name = archive_name.replace("{now}", datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
            archive_name = archive_name.replace("{date}", datetime.now().strftime('%Y-%m-%d'))
            archive_name = archive_name.replace("{time}", datetime.now().strftime('%H:%M:%S'))
            archive_name = archive_name.replace("{timestamp}", str(int(datetime.now().timestamp())))
        else:
            # Default template if none specified: use job name
            archive_name = f"{job.name}-{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"

        # Execute backup with optional prune/compact asynchronously (non-blocking)
        asyncio.create_task(
            execute_scheduled_backup_with_maintenance(
                backup_job.id,
                job.repository,
                job.id,
                archive_name=archive_name
            )
        )

        # Update last run time
        job.last_run = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Scheduled job run manually", job_id=job_id, user=current_user.username, backup_job_id=backup_job.id)

        return {
            "job_id": backup_job.id,
            "status": "pending",
            "message": "Scheduled job started successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to run scheduled job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to run scheduled job: {str(e)}")

@router.post("/validate-cron")
async def validate_cron_expression(
    cron_data: CronExpression,
    current_user: User = Depends(get_current_user)
):
    """Validate and preview cron expression"""
    try:
        # Build cron expression
        cron_expr = f"{cron_data.minute} {cron_data.hour} {cron_data.day_of_month} {cron_data.month} {cron_data.day_of_week}"
        
        # Validate cron expression
        try:
            cron = croniter.croniter(cron_expr, datetime.now(timezone.utc))
        except Exception as e:
            return {
                "success": False,
                "error": f"Invalid cron expression: {str(e)}",
                "cron_expression": cron_expr
            }
        
        # Get next 10 run times
        next_runs = []
        for i in range(10):
            next_dt = cron.get_next(datetime)
            next_runs.append(serialize_datetime(next_dt))

        return {
            "success": True,
            "cron_expression": cron_expr,
            "next_runs": next_runs,
            "description": croniter.croniter(cron_expr).description
        }
    except Exception as e:
        logger.error("Failed to validate cron expression", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to validate cron expression: {str(e)}")

# Background task to check and run scheduled jobs
async def execute_scheduled_backup_with_maintenance(backup_job_id: int, repository_path: str,
                                                     scheduled_job_id: int, archive_name: str = None):
    """Execute backup and optionally run prune/compact after successful backup

    Args:
        backup_job_id: Backup job ID
        repository_path: Repository path
        scheduled_job_id: Scheduled job ID
        archive_name: Optional custom archive name
    """
    from app.database.models import Repository, BackupJob
    from app.services.backup_service import backup_service

    db = next(get_db())
    try:
        # Execute the backup with custom archive name if provided
        await backup_service.execute_backup(backup_job_id, repository_path, db, archive_name=archive_name)

        # Check if backup was successful (or completed with warnings)
        backup_job = db.query(BackupJob).filter(BackupJob.id == backup_job_id).first()
        if not backup_job or backup_job.status not in ["completed", "completed_with_warnings"]:
            logger.info("Backup did not complete successfully, skipping prune/compact",
                       backup_job_id=backup_job_id, backup_status=backup_job.status if backup_job else "None")
            return

        # Get scheduled job to check prune/compact settings
        scheduled_job = db.query(ScheduledJob).filter(ScheduledJob.id == scheduled_job_id).first()
        if not scheduled_job:
            return

        # Get repository info for prune/compact
        repo = db.query(Repository).filter(Repository.path == repository_path).first()
        if not repo:
            logger.error("Repository not found for prune/compact", repository=repository_path)
            return

        # Run prune if enabled
        if scheduled_job.run_prune_after:
            try:
                logger.info("Running scheduled prune", scheduled_job_id=scheduled_job_id, repository=repository_path)

                # Create a PruneJob record for tracking and activity feed
                prune_job = PruneJob(
                    repository_id=repo.id,
                    repository_path=repo.path,
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(prune_job)
                db.commit()
                db.refresh(prune_job)

                # Update backup job status to show prune is running
                backup_job.maintenance_status = "running_prune"
                db.commit()

                prune_result = await borg.prune_archives(
                    repository=repo.path,
                    keep_hourly=scheduled_job.prune_keep_hourly,
                    keep_daily=scheduled_job.prune_keep_daily,
                    keep_weekly=scheduled_job.prune_keep_weekly,
                    keep_monthly=scheduled_job.prune_keep_monthly,
                    keep_quarterly=scheduled_job.prune_keep_quarterly,
                    keep_yearly=scheduled_job.prune_keep_yearly,
                    dry_run=False,
                    remote_path=repo.remote_path,
                    passphrase=repo.passphrase
                )

                if prune_result.get("success"):
                    scheduled_job.last_prune = datetime.now(timezone.utc)
                    backup_job.maintenance_status = "prune_completed"

                    # Update PruneJob record
                    prune_job.status = "completed"
                    prune_job.completed_at = datetime.now(timezone.utc)
                    prune_job.logs = "Scheduled prune completed successfully"

                    db.commit()
                    logger.info("Scheduled prune completed", scheduled_job_id=scheduled_job_id, prune_job_id=prune_job.id)
                else:
                    backup_job.maintenance_status = "prune_failed"

                    # Update PruneJob record
                    prune_job.status = "failed"
                    prune_job.completed_at = datetime.now(timezone.utc)
                    prune_job.error_message = prune_result.get("stderr", "Unknown error")
                    prune_job.logs = prune_result.get("stderr", "")

                    db.commit()
                    logger.error("Scheduled prune failed", scheduled_job_id=scheduled_job_id, prune_job_id=prune_job.id,
                                error=prune_result.get("stderr"))

            except Exception as e:
                backup_job.maintenance_status = "prune_failed"

                # Update PruneJob record if it was created
                try:
                    if 'prune_job' in locals():
                        prune_job.status = "failed"
                        prune_job.completed_at = datetime.now(timezone.utc)
                        prune_job.error_message = str(e)
                except:
                    pass

                db.commit()
                logger.error("Failed to run scheduled prune", scheduled_job_id=scheduled_job_id, error=str(e))

        # Run compact if enabled (only after successful prune or if prune not enabled)
        if scheduled_job.run_compact_after and (scheduled_job.run_prune_after or not scheduled_job.run_prune_after):
            try:
                logger.info("Running scheduled compact", scheduled_job_id=scheduled_job_id, repository=repository_path)

                # Create a CompactJob record for tracking and activity feed
                compact_job = CompactJob(
                    repository_id=repo.id,
                    repository_path=repo.path,
                    status="running",
                    started_at=datetime.now(timezone.utc)
                )
                db.add(compact_job)
                db.commit()
                db.refresh(compact_job)

                # Update backup job status to show compact is running
                backup_job.maintenance_status = "running_compact"
                db.commit()

                compact_result = await borg.compact_repository(
                    repository=repo.path,
                    remote_path=repo.remote_path,
                    passphrase=repo.passphrase
                )

                if compact_result.get("success"):
                    scheduled_job.last_compact = datetime.now(timezone.utc)
                    backup_job.maintenance_status = "compact_completed"

                    # Update CompactJob record
                    compact_job.status = "completed"
                    compact_job.completed_at = datetime.now(timezone.utc)
                    compact_job.logs = "Scheduled compact completed successfully"

                    db.commit()
                    logger.info("Scheduled compact completed", scheduled_job_id=scheduled_job_id, compact_job_id=compact_job.id)
                else:
                    backup_job.maintenance_status = "compact_failed"

                    # Update CompactJob record
                    compact_job.status = "failed"
                    compact_job.completed_at = datetime.now(timezone.utc)
                    compact_job.error_message = compact_result.get("stderr", "Unknown error")
                    compact_job.logs = compact_result.get("stderr", "")

                    db.commit()
                    logger.error("Scheduled compact failed", scheduled_job_id=scheduled_job_id, compact_job_id=compact_job.id,
                                error=compact_result.get("stderr"))

            except Exception as e:
                backup_job.maintenance_status = "compact_failed"

                # Update CompactJob record if it was created
                try:
                    if 'compact_job' in locals():
                        compact_job.status = "failed"
                        compact_job.completed_at = datetime.now(timezone.utc)
                        compact_job.error_message = str(e)
                except:
                    pass

                db.commit()
                logger.error("Failed to run scheduled compact", scheduled_job_id=scheduled_job_id, error=str(e))

        # Mark maintenance as fully completed if we got this far
        if backup_job.maintenance_status and "failed" not in backup_job.maintenance_status:
            backup_job.maintenance_status = "maintenance_completed"
            db.commit()

    finally:
        db.close()

async def check_scheduled_jobs():
    """Check and execute scheduled jobs"""
    while True:
        try:
            db = next(get_db())
            jobs = db.query(ScheduledJob).filter(
                ScheduledJob.enabled == True,
                ScheduledJob.next_run <= datetime.now(timezone.utc)
            ).all()

            for job in jobs:
                try:
                    logger.info("Running scheduled job", job_id=job.id, name=job.name)

                    # Get repository info
                    from app.database.models import Repository, BackupJob
                    from app.services.backup_service import backup_service

                    repo = db.query(Repository).filter(Repository.path == job.repository).first()
                    if not repo:
                        logger.error("Repository not found for scheduled job", job_id=job.id, repository=job.repository)
                        continue

                    # Create backup job record with scheduled_job_id
                    backup_job = BackupJob(
                        repository=job.repository or "default",
                        status="pending",
                        scheduled_job_id=job.id  # Link to scheduled job
                    )
                    db.add(backup_job)
                    db.commit()
                    db.refresh(backup_job)

                    # Generate archive name from template
                    archive_name = None
                    if job.archive_name_template:
                        # Replace template placeholders
                        archive_name = job.archive_name_template
                        archive_name = archive_name.replace("{job_name}", job.name)
                        archive_name = archive_name.replace("{now}", datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
                        archive_name = archive_name.replace("{date}", datetime.now().strftime('%Y-%m-%d'))
                        archive_name = archive_name.replace("{time}", datetime.now().strftime('%H:%M:%S'))
                        archive_name = archive_name.replace("{timestamp}", str(int(datetime.now().timestamp())))
                    else:
                        # Default template if none specified: use job name
                        archive_name = f"{job.name}-{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"

                    # Execute backup with optional prune/compact asynchronously (non-blocking)
                    asyncio.create_task(
                        execute_scheduled_backup_with_maintenance(
                            backup_job.id,
                            job.repository,
                            job.id,
                            archive_name=archive_name
                        )
                    )

                    # Update job status
                    job.last_run = datetime.now(timezone.utc)

                    # Calculate next run time
                    cron = croniter.croniter(job.cron_expression, datetime.now(timezone.utc))
                    job.next_run = cron.get_next(datetime)

                    db.commit()

                    logger.info("Scheduled job started", job_id=job.id, name=job.name, backup_job_id=backup_job.id)

                except Exception as e:
                    logger.error("Failed to run scheduled job", job_id=job.id, error=str(e))
                    # Update last run time even if failed
                    job.last_run = datetime.now(timezone.utc)
                    db.commit()

                    # Send failure notification
                    try:
                        asyncio.create_task(
                            notification_service.send_schedule_failure(
                                db, job.name, job.repository, str(e)
                            )
                        )
                    except Exception as notif_error:
                        logger.warning("Failed to send schedule failure notification", error=str(notif_error))

            db.close()

        except Exception as e:
            logger.error("Error in scheduled job checker", error=str(e))

        # Wait for 1 minute before next check
        await asyncio.sleep(60) 