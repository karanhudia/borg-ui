from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import psutil
import structlog
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from app.database.database import get_db
from app.database.models import User, BackupJob
from app.core.security import get_current_user
from app.core.borg import borg
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter()

# Helper function to format datetime with timezone
def format_datetime(dt):
    """Format datetime to ISO8601 with UTC timezone indicator"""
    return serialize_datetime(dt)

# Pydantic models for responses
class SystemMetrics(BaseModel):
    cpu_usage: float
    memory_usage: float
    memory_total: int
    memory_available: int
    disk_usage: float
    disk_total: int
    disk_free: int
    uptime: int

class ScheduledJobInfo(BaseModel):
    id: int
    name: str
    cron_expression: str
    repository: str = None
    enabled: bool
    last_run: str = None
    next_run: str = None

class DashboardStatus(BaseModel):
    system_metrics: SystemMetrics
    scheduled_jobs: List[ScheduledJobInfo]
    recent_jobs: List[Dict[str, Any]]
    alerts: List[Dict[str, Any]]
    last_updated: str

class MetricsResponse(BaseModel):
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: Dict[str, float]
    load_average: List[float]

class ScheduleResponse(BaseModel):
    jobs: List[ScheduledJobInfo]
    next_execution: str = None


def get_system_metrics() -> SystemMetrics:
    """Get system resource metrics"""
    try:
        # CPU usage
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Disk usage
        disk = psutil.disk_usage('/')
        
        # System uptime
        uptime = int(psutil.boot_time())
        
        return SystemMetrics(
            cpu_usage=cpu_usage,
            memory_usage=memory.percent,
            memory_total=memory.total,
            memory_available=memory.available,
            disk_usage=disk.percent,
            disk_total=disk.total,
            disk_free=disk.free,
            uptime=uptime
        )
    except Exception as e:
        logger.error("Failed to get system metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get system metrics"
        )

def get_scheduled_jobs(db: Session) -> List[ScheduledJobInfo]:
    """Get scheduled jobs information"""
    # TODO: Implement when ScheduledJob model is added back
    return []

def get_recent_jobs(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent backup jobs"""
    try:
        jobs = db.query(BackupJob).order_by(BackupJob.started_at.desc()).limit(limit).all()
        job_list = []

        for job in jobs:
            # Determine trigger type
            triggered_by = 'schedule' if job.scheduled_job_id else 'manual'

            job_list.append({
                "id": job.id,
                "repository": job.repository,
                "status": job.status,
                "started_at": format_datetime(job.started_at),
                "completed_at": format_datetime(job.completed_at),
                "progress": job.progress,
                "error_message": job.error_message,
                "triggered_by": triggered_by,
                "schedule_id": job.scheduled_job_id,
                "has_logs": bool(job.log_file_path or job.logs)
            })

        return job_list
    except Exception as e:
        logger.error("Failed to get recent jobs", error=str(e))
        return []

def get_alerts(db: Session, hours: int = 24) -> List[Dict[str, Any]]:
    """Get recent system alerts"""
    # TODO: Implement when SystemLog model is added back
    return []

@router.get("/status", response_model=DashboardStatus)
async def get_dashboard_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive dashboard status"""
    try:
        # Get system metrics
        system_metrics = get_system_metrics()

        # Get scheduled jobs
        scheduled_jobs = get_scheduled_jobs(db)

        # Get recent jobs
        recent_jobs = get_recent_jobs(db)

        # Get alerts
        alerts = get_alerts(db)

        return DashboardStatus(
            system_metrics=system_metrics,
            scheduled_jobs=scheduled_jobs,
            recent_jobs=recent_jobs,
            alerts=alerts,
            last_updated=format_datetime(datetime.utcnow())
        )
    except Exception as e:
        logger.error("Error getting dashboard status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dashboard status"
        )

@router.get("/metrics", response_model=MetricsResponse)
async def get_dashboard_metrics(current_user: User = Depends(get_current_user)):
    """Get system metrics for dashboard"""
    try:
        # CPU usage
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Disk usage
        disk = psutil.disk_usage('/')
        
        # Network I/O
        network = psutil.net_io_counters()
        
        # Load average
        load_avg = psutil.getloadavg()
        
        return MetricsResponse(
            cpu_usage=cpu_usage,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            network_io={
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv
            },
            load_average=list(load_avg)
        )
    except Exception as e:
        logger.error("Error getting metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get metrics"
        )

@router.get("/schedule", response_model=ScheduleResponse)
async def get_dashboard_schedule(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get scheduled jobs information"""
    try:
        jobs = get_scheduled_jobs(db)
        
        # Find next execution time
        next_execution = None
        if jobs:
            # This is a simplified approach - in a real implementation,
            # you'd use a proper cron parser to calculate next execution
            next_execution = format_datetime(datetime.utcnow())
        
        return ScheduleResponse(
            jobs=jobs,
            next_execution=next_execution
        )
    except Exception as e:
        logger.error("Error getting schedule", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get schedule"
        )

