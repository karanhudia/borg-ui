from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import structlog
import croniter
import json
import os
import asyncio

from app.database.database import get_db
from app.database.models import User
from app.core.security import get_current_user
from app.core.borg import BorgInterface
from app.config import settings

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
    config_file: Optional[str] = None
    enabled: bool = True
    description: Optional[str] = None

class ScheduledJobUpdate(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    repository: Optional[str] = None
    config_file: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None

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
                    "last_run": job.last_run.isoformat() if job.last_run else None,
                    "next_run": job.next_run.isoformat() if job.next_run else None,
                    "created_at": job.created_at.isoformat(),
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                    "description": job.description
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
            cron = croniter.croniter(job_data.cron_expression, datetime.now())
            next_run = cron.get_next(datetime)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid cron expression: {str(e)}")
        
        # Check if job name already exists
        existing_job = db.query(ScheduledJob).filter(ScheduledJob.name == job_data.name).first()
        if existing_job:
            raise HTTPException(status_code=400, detail="Job name already exists")
        
        # Create scheduled job
        scheduled_job = ScheduledJob(
            name=job_data.name,
            cron_expression=job_data.cron_expression,
            repository=job_data.repository,
            config_file=job_data.config_file,
            enabled=job_data.enabled,
            next_run=next_run,
            description=job_data.description
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
                "next_run": scheduled_job.next_run.isoformat() if scheduled_job.next_run else None
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
        
        end_time = datetime.now() + timedelta(hours=hours)
        
        for job in jobs:
            try:
                cron = croniter.croniter(job.cron_expression, datetime.now())
                next_run = cron.get_next(datetime)
                
                if next_run <= end_time:
                    upcoming_jobs.append({
                        "id": job.id,
                        "name": job.name,
                        "repository": job.repository,
                        "next_run": next_run.isoformat(),
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
            cron = croniter.croniter(job.cron_expression, datetime.now())
            next_runs = []
            for i in range(5):  # Get next 5 run times
                next_runs.append(cron.get_next(datetime).isoformat())
        except:
            next_runs = []
        
        return {
            "success": True,
            "job": {
                "id": job.id,
                "name": job.name,
                "cron_expression": job.cron_expression,
                "repository": job.repository,
                "config_file": job.config_file,
                "enabled": job.enabled,
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "next_run": job.next_run.isoformat() if job.next_run else None,
                "next_runs": next_runs,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                "description": job.description
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
                cron = croniter.croniter(job_data.cron_expression, datetime.now())
                job.cron_expression = job_data.cron_expression
                job.next_run = cron.get_next(datetime)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid cron expression: {str(e)}")
        
        if job_data.repository is not None:
            job.repository = job_data.repository
        
        if job_data.config_file is not None:
            job.config_file = job_data.config_file
        
        if job_data.enabled is not None:
            job.enabled = job_data.enabled
        
        if job_data.description is not None:
            job.description = job_data.description
        
        job.updated_at = datetime.utcnow()
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
        job.updated_at = datetime.utcnow()
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
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        
        # Execute backup
        result = await borg.run_backup(
            repository=job.repository,
            config_file=job.config_file
        )
        
        # Update last run time
        job.last_run = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info("Scheduled job run manually", job_id=job_id, user=current_user.username)
        
        return {
            "success": True,
            "message": "Scheduled job executed successfully",
            "result": result
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
            cron = croniter.croniter(cron_expr, datetime.now())
        except Exception as e:
            return {
                "success": False,
                "error": f"Invalid cron expression: {str(e)}",
                "cron_expression": cron_expr
            }
        
        # Get next 10 run times
        next_runs = []
        for i in range(10):
            next_runs.append(cron.get_next(datetime).isoformat())
        
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
async def check_scheduled_jobs():
    """Check and execute scheduled jobs"""
    while True:
        try:
            db = next(get_db())
            jobs = db.query(ScheduledJob).filter(
                ScheduledJob.enabled == True,
                ScheduledJob.next_run <= datetime.now()
            ).all()
            
            for job in jobs:
                try:
                    logger.info("Running scheduled job", job_id=job.id, name=job.name)
                    
                    # Execute backup
                    result = await borg.run_backup(
                        repository=job.repository,
                        config_file=job.config_file
                    )
                    
                    # Update job status
                    job.last_run = datetime.now()
                    
                    # Calculate next run time
                    cron = croniter.croniter(job.cron_expression, datetime.now())
                    job.next_run = cron.get_next(datetime)
                    
                    db.commit()
                    
                    logger.info("Scheduled job completed", job_id=job.id, name=job.name, success=result["success"])
                    
                except Exception as e:
                    logger.error("Failed to run scheduled job", job_id=job.id, error=str(e))
                    # Update last run time even if failed
                    job.last_run = datetime.now()
                    db.commit()
            
            db.close()
            
        except Exception as e:
            logger.error("Error in scheduled job checker", error=str(e))
        
        # Wait for 1 minute before next check
        await asyncio.sleep(60) 