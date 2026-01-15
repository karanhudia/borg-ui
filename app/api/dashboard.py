from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import psutil
import structlog
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from app.database.database import get_db
from app.database.models import User, BackupJob, Repository, Schedule, CheckJob, CompactJob, PruneJob, SSHConnection
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


@router.get("/overview")
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive dashboard overview with repository health, trends, and maintenance alerts"""
    try:
        now = datetime.utcnow()

        # Get all repositories
        repositories = db.query(Repository).all()

        # Get all schedules
        schedules = db.query(Schedule).all()

        # Get SSH connections
        ssh_connections = db.query(SSHConnection).all()

        # Calculate repository health
        repo_health = []
        total_size_bytes = 0
        total_archives = 0

        for repo in repositories:
            # Parse size
            size_bytes = parse_size_to_bytes(repo.total_size)
            total_size_bytes += size_bytes
            total_archives += repo.archive_count or 0

            # Determine health status
            health_status = "healthy"
            health_color = "success"
            warnings = []

            # Check last backup
            if repo.last_backup:
                days_since_backup = (now - repo.last_backup).days
                if days_since_backup > 7:
                    health_status = "critical"
                    health_color = "error"
                    warnings.append(f"No backup in {days_since_backup} days")
                elif days_since_backup > 3:
                    health_status = "warning"
                    health_color = "warning"
                    warnings.append(f"Last backup {days_since_backup} days ago")
            else:
                health_status = "critical"
                health_color = "error"
                warnings.append("Never backed up")

            # Check last check
            if repo.last_check:
                days_since_check = (now - repo.last_check).days
                if days_since_check > 30:
                    if health_status == "healthy":
                        health_status = "warning"
                        health_color = "warning"
                    warnings.append(f"Check overdue ({days_since_check}d ago)")
            else:
                if health_status == "healthy":
                    health_status = "warning"
                    health_color = "warning"
                warnings.append("Never checked")

            # Check last compact
            if repo.last_compact:
                days_since_compact = (now - repo.last_compact).days
                if days_since_compact > 60:
                    warnings.append(f"Compact recommended ({days_since_compact}d ago)")
            else:
                warnings.append("Never compacted")

            # Get associated schedule
            repo_schedule = next((s for s in schedules if repo.id in s.repository_ids), None) if hasattr(schedules[0] if schedules else None, 'repository_ids') else None

            # Calculate dedup ratio (if we have the data)
            dedup_ratio = None
            if hasattr(repo, 'deduplicated_size') and repo.deduplicated_size and size_bytes > 0:
                dedup_bytes = parse_size_to_bytes(repo.deduplicated_size)
                dedup_ratio = int((1 - (dedup_bytes / size_bytes)) * 100) if size_bytes > 0 else 0

            repo_health.append({
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "type": repo.repository_type or "local",
                "last_backup": serialize_datetime(repo.last_backup),
                "last_check": serialize_datetime(repo.last_check),
                "last_compact": serialize_datetime(repo.last_compact),
                "archive_count": repo.archive_count or 0,
                "total_size": repo.total_size,
                "size_bytes": size_bytes,
                "health_status": health_status,
                "health_color": health_color,
                "warnings": warnings,
                "dedup_ratio": dedup_ratio,
                "has_schedule": repo_schedule is not None,
                "schedule_enabled": repo_schedule.enabled if repo_schedule else False,
            })

        # Calculate backup success rate (last 30 days)
        thirty_days_ago = now - timedelta(days=30)
        recent_jobs = db.query(BackupJob).filter(BackupJob.started_at >= thirty_days_ago).all()

        total_jobs = len(recent_jobs)
        successful_jobs = len([j for j in recent_jobs if j.status == "completed"])
        failed_jobs = len([j for j in recent_jobs if j.status == "failed"])
        success_rate = (successful_jobs / total_jobs * 100) if total_jobs > 0 else 0

        # Group jobs by week for trend
        backup_trends = []
        for week in range(4):
            week_start = now - timedelta(days=(4-week)*7)
            week_end = week_start + timedelta(days=7)
            week_jobs = [j for j in recent_jobs if week_start <= j.started_at < week_end]
            week_success = len([j for j in week_jobs if j.status == "completed"])
            week_total = len(week_jobs)
            week_rate = (week_success / week_total * 100) if week_total > 0 else 0

            backup_trends.append({
                "week": f"Week {week + 1}",
                "success_rate": round(week_rate, 1),
                "successful": week_success,
                "failed": len([j for j in week_jobs if j.status == "failed"]),
                "total": week_total
            })

        # Get upcoming schedules (next 24 hours)
        active_schedules = [s for s in schedules if s.enabled]
        upcoming_tasks = []
        for schedule in active_schedules[:10]:  # Limit to 10
            upcoming_tasks.append({
                "id": schedule.id,
                "name": schedule.name,
                "repositories": schedule.repository_ids if hasattr(schedule, 'repository_ids') else [],
                "cron": schedule.cron_expression,
                "next_run": "Calculating...",  # Would need croniter to calculate
            })

        # Get maintenance alerts
        maintenance_alerts = []

        # Check repos needing maintenance
        for repo in repositories:
            if repo.last_check:
                days_since_check = (now - repo.last_check).days
                if days_since_check > 30:
                    maintenance_alerts.append({
                        "type": "check_overdue",
                        "severity": "warning" if days_since_check < 60 else "error",
                        "repository": repo.name,
                        "repository_id": repo.id,
                        "message": f"Check overdue by {days_since_check} days",
                        "action": "schedule_check"
                    })
            else:
                maintenance_alerts.append({
                    "type": "check_never",
                    "severity": "warning",
                    "repository": repo.name,
                    "repository_id": repo.id,
                    "message": "Never checked",
                    "action": "schedule_check"
                })

            if repo.last_compact:
                days_since_compact = (now - repo.last_compact).days
                if days_since_compact > 60:
                    maintenance_alerts.append({
                        "type": "compact_recommended",
                        "severity": "info",
                        "repository": repo.name,
                        "repository_id": repo.id,
                        "message": f"Compact recommended ({days_since_compact}d ago)",
                        "action": "schedule_compact"
                    })
            else:
                maintenance_alerts.append({
                    "type": "compact_never",
                    "severity": "info",
                    "repository": repo.name,
                    "repository_id": repo.id,
                    "message": "Never compacted",
                    "action": "schedule_compact"
                })

        # Get recent activity (last 10 jobs across all types)
        recent_backups = db.query(BackupJob).order_by(BackupJob.started_at.desc()).limit(5).all()
        recent_checks = db.query(CheckJob).order_by(CheckJob.started_at.desc()).limit(3).all()
        recent_compacts = db.query(CompactJob).order_by(CompactJob.started_at.desc()).limit(2).all()

        activity_feed = []

        for job in recent_backups:
            activity_feed.append({
                "id": job.id,
                "type": "backup",
                "status": job.status,
                "repository": job.repository,
                "timestamp": serialize_datetime(job.started_at),
                "message": f"Backup {job.status}",
                "error": job.error_message if job.status == "failed" else None
            })

        for job in recent_checks:
            activity_feed.append({
                "id": job.id,
                "type": "check",
                "status": job.status,
                "repository": job.repository_path,
                "timestamp": serialize_datetime(job.started_at),
                "message": f"Check {job.status}",
                "error": job.error_message if job.status == "failed" else None
            })

        for job in recent_compacts:
            activity_feed.append({
                "id": job.id,
                "type": "compact",
                "status": job.status,
                "repository": job.repository_path,
                "timestamp": serialize_datetime(job.started_at),
                "message": f"Compact {job.status}" + (f" - Freed {job.space_freed}" if job.space_freed else ""),
                "freed_space": job.space_freed if job.status == "completed" else None
            })

        # Sort activity by timestamp
        activity_feed.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        activity_feed = activity_feed[:10]

        # Count SSH connections
        ssh_active = len([c for c in ssh_connections if c.is_active])
        ssh_total = len(ssh_connections)

        # Get system metrics
        system_metrics = get_system_metrics()

        return {
            "summary": {
                "total_repositories": len(repositories),
                "local_repositories": len([r for r in repositories if r.repository_type == "local"]),
                "ssh_repositories": len([r for r in repositories if r.repository_type == "ssh"]),
                "active_schedules": len([s for s in schedules if s.enabled]),
                "total_schedules": len(schedules),
                "ssh_connections_active": ssh_active,
                "ssh_connections_total": ssh_total,
                "success_rate_30d": round(success_rate, 1),
                "successful_jobs_30d": successful_jobs,
                "failed_jobs_30d": failed_jobs,
                "total_jobs_30d": total_jobs,
            },
            "storage": {
                "total_size": format_bytes(total_size_bytes),
                "total_size_bytes": total_size_bytes,
                "total_archives": total_archives,
                "average_dedup_ratio": calculate_average_dedup(repositories),
            },
            "repository_health": sorted(repo_health, key=lambda x: (
                0 if x["health_status"] == "critical" else 1 if x["health_status"] == "warning" else 2
            )),
            "backup_trends": backup_trends,
            "upcoming_tasks": upcoming_tasks,
            "maintenance_alerts": maintenance_alerts[:10],
            "activity_feed": activity_feed,
            "system_metrics": system_metrics.dict(),
            "last_updated": serialize_datetime(now),
        }

    except Exception as e:
        logger.error("Error getting dashboard overview", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard overview: {str(e)}"
        )


def parse_size_to_bytes(size_str: str) -> int:
    """Parse human-readable size string to bytes"""
    if not size_str:
        return 0

    size_str = size_str.strip().upper()

    # Remove spaces
    size_str = size_str.replace(" ", "")

    multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024**2,
        'GB': 1024**3,
        'TB': 1024**4,
        'PB': 1024**5,
    }

    for unit, multiplier in multipliers.items():
        if size_str.endswith(unit):
            try:
                number = float(size_str[:-len(unit)])
                return int(number * multiplier)
            except ValueError:
                return 0

    # Try parsing as plain number
    try:
        return int(float(size_str))
    except ValueError:
        return 0


def format_bytes(bytes_value: int) -> str:
    """Format bytes to human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def calculate_average_dedup(repositories: List[Repository]) -> int:
    """Calculate average deduplication ratio across repositories"""
    # This is a placeholder - would need actual dedup data from borg info
    # For now, return None to indicate we don't have this data
    return None

