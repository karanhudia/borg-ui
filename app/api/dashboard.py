from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import psutil
import structlog
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.database.database import get_db
from app.database.models import User, BackupJob
from app.core.security import get_current_user
from app.core.borg import borg

logger = structlog.get_logger()
router = APIRouter()

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

class BackupStatus(BaseModel):
    repository: str
    status: str
    last_backup: str = "Never"
    archive_count: int = 0
    total_size: str = "0"
    health: str = "unknown"

class ScheduledJobInfo(BaseModel):
    id: int
    name: str
    cron_expression: str
    repository: str = None
    enabled: bool
    last_run: str = None
    next_run: str = None

class DashboardStatus(BaseModel):
    backup_status: List[BackupStatus]
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

class HealthResponse(BaseModel):
    status: str
    checks: Dict[str, Dict[str, Any]]
    timestamp: str

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

async def get_backup_status() -> List[BackupStatus]:
    """Get backup status for all repositories"""
    try:
        repo_status = await borg.get_repository_status()
        if not repo_status["success"]:
            logger.warning("Failed to get repository status", error=repo_status.get("error"))
            return []
        
        status_list = []
        for repo in repo_status["repositories"]:
            status_list.append(BackupStatus(
                repository=repo["name"],
                status=repo["status"],
                last_backup=repo["last_backup"],
                archive_count=repo["archive_count"],
                total_size=repo["total_size"],
                health=repo["status"]
            ))
        
        return status_list
    except Exception as e:
        logger.error("Failed to get backup status", error=str(e))
        return []

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
            job_list.append({
                "id": job.id,
                "repository": job.repository,
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "progress": job.progress,
                "error_message": job.error_message
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
        # Get backup status
        backup_status = await get_backup_status()
        
        # Get system metrics
        system_metrics = get_system_metrics()
        
        # Get scheduled jobs
        scheduled_jobs = get_scheduled_jobs(db)
        
        # Get recent jobs
        recent_jobs = get_recent_jobs(db)
        
        # Get alerts
        alerts = get_alerts(db)
        
        return DashboardStatus(
            backup_status=backup_status,
            system_metrics=system_metrics,
            scheduled_jobs=scheduled_jobs,
            recent_jobs=recent_jobs,
            alerts=alerts,
            last_updated=datetime.utcnow().isoformat()
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
            next_execution = datetime.utcnow().isoformat()
        
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

@router.get("/health", response_model=HealthResponse)
async def get_dashboard_health(current_user: User = Depends(get_current_user)):
    """Get system health status"""
    try:
        checks = {}
        
        # Check system resources
        try:
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            checks["system"] = {
                "status": "healthy" if cpu_usage < 90 and memory.percent < 90 and disk.percent < 90 else "warning",
                "cpu_usage": cpu_usage,
                "memory_usage": memory.percent,
                "disk_usage": disk.percent
            }
        except Exception as e:
            checks["system"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check borg availability
        try:
            system_info = await borg.get_system_info()
            checks["borg"] = {
                "status": "healthy" if system_info["success"] else "error",
                "version": system_info.get("borg_version", "Unknown"),
                "data_dir": system_info.get("data_dir", "Unknown")
            }
        except Exception as e:
            checks["borg"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check backup repositories
        try:
            repo_status = await borg.get_repository_status()
            if repo_status["success"]:
                healthy_repos = sum(1 for repo in repo_status["repositories"] if repo["status"] == "healthy")
                total_repos = len(repo_status["repositories"])
                
                # If no repositories are configured, that's fine - not a warning
                if total_repos == 0:
                    checks["repositories"] = {
                        "status": "healthy",
                        "healthy_count": 0,
                        "total_count": 0,
                        "message": "No repositories configured"
                    }
                else:
                    checks["repositories"] = {
                        "status": "healthy" if healthy_repos == total_repos else "warning",
                        "healthy_count": healthy_repos,
                        "total_count": total_repos
                    }
            else:
                checks["repositories"] = {
                    "status": "error",
                    "error": repo_status.get("error", "Unknown error")
                }
        except Exception as e:
            checks["repositories"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Overall status
        overall_status = "healthy"
        if any(check["status"] == "error" for check in checks.values()):
            overall_status = "error"
        elif any(check["status"] == "warning" for check in checks.values()):
            overall_status = "warning"
        
        return HealthResponse(
            status=overall_status,
            checks=checks,
            timestamp=datetime.utcnow().isoformat()
        )
    except Exception as e:
        logger.error("Error getting health status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get health status"
        ) 