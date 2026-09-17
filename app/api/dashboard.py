from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, exists, func, or_
from sqlalchemy.orm import Session
from pydantic import BaseModel
import psutil
import structlog
import threading
import time
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database.database import get_db
from app.database.models import (
    User,
    BackupPlan,
    BackupPlanRepository,
    Operation,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
    SSHConnection,
    SystemSettings,
)
from app.core.security import get_current_user
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations.backup_facade import recent_backup_jobs
from app.services.operations.job_facade import (
    UNSETTLED_STATUSES,
    MaintenanceJobFacade,
    NEEDS_BACKUP,
    latest_maintenance_jobs_by_repository,
    legacy_status,
)
from app.services.storage_usage import format_bytes, stored_size_bytes
from app.utils.datetime_utils import serialize_datetime
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    calculate_next_cron_run,
    to_utc_naive,
)

logger = structlog.get_logger()
router = APIRouter()


class CpuSampler:
    """CPU load as the share of busy time between two `psutil.cpu_times()`
    snapshots, one reading per `MIN_SECONDS` shared by every caller.

    Not `psutil.cpu_percent(interval=None)`: that keeps its baseline per
    thread, and the overview runs on whichever threadpool worker takes the
    request, so a worker's first reading would be a meaningless 0.0 and
    two requests in one tick would show the second one an idle CPU. Not
    `interval=1` either, which slept a second on the event loop. The first
    reading after start averages the time since import."""

    MIN_SECONDS = 2.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._read_at: Optional[float] = None
        self._value = 0.0
        try:
            self._times = psutil.cpu_times()
        except Exception:  # pragma: no cover - a host without CPU counters
            self._times = None

    @staticmethod
    def _busy_and_total(times) -> tuple[float, float]:
        """Busy and total CPU seconds of a `cpu_times` tuple, as psutil
        counts them: idle and I/O wait are not busy, guest time is already
        inside user time."""
        total = sum(times)
        total -= getattr(times, "guest", 0) + getattr(times, "guest_nice", 0)
        busy = total - times.idle - getattr(times, "iowait", 0)
        return busy, total

    def read(self) -> float:
        with self._lock:
            now = time.monotonic()
            if self._read_at is not None and now - self._read_at < self.MIN_SECONDS:
                return self._value
            times = psutil.cpu_times()
            if self._times is not None:
                busy_before, total_before = self._busy_and_total(self._times)
                busy, total = self._busy_and_total(times)
                elapsed = total - total_before
                if elapsed > 0:
                    self._value = round(
                        min(100.0, max(0.0, (busy - busy_before) / elapsed * 100)), 1
                    )
            self._times = times
            self._read_at = now
            return self._value


_cpu_sampler = CpuSampler()


RESTORE_CHECK_WARNING_DAYS = 14
RESTORE_CHECK_CRITICAL_DAYS = 30


@dataclass(frozen=True)
class DashboardHealthThresholds:
    backup_warning_days: int = 3
    backup_critical_days: int = 7
    check_warning_days: int = 7
    check_critical_days: int = 30
    compact_warning_days: int = 30
    compact_critical_days: int = 60
    restore_check_warning_days: int = RESTORE_CHECK_WARNING_DAYS
    restore_check_critical_days: int = RESTORE_CHECK_CRITICAL_DAYS
    observe_freshness_warning_days: int = 2
    observe_freshness_critical_days: int = 7

    @classmethod
    def from_settings(
        cls, settings: Optional[SystemSettings]
    ) -> "DashboardHealthThresholds":
        if not settings:
            return cls()

        values = {}
        for field in fields(cls):
            settings_name = f"dashboard_{field.name}"
            value = getattr(settings, settings_name, None)
            values[field.name] = field.default if value is None else value

        return cls(**values)


# Helper function to format datetime with timezone
def format_datetime(dt):
    """Format datetime to ISO8601 with UTC timezone indicator"""
    return serialize_datetime(dt)


def resolve_schedule_next_run(
    schedule: ScheduledJob, now: datetime
) -> Optional[datetime]:
    """Resolve the next due time for a schedule, preferring stored future values."""
    now_utc = to_utc_naive(now)
    if schedule.next_run and to_utc_naive(schedule.next_run) > now_utc:
        return to_utc_naive(schedule.next_run)

    try:
        return calculate_next_cron_run(
            schedule.cron_expression,
            now_utc,
            schedule.timezone or DEFAULT_SCHEDULE_TIMEZONE,
        )
    except Exception:
        return None


def resolve_backup_plan_next_run(plan: BackupPlan, now: datetime) -> Optional[datetime]:
    """Resolve the next due time for a backup plan, preferring stored future values."""
    now_utc = to_utc_naive(now)
    if plan.next_run and to_utc_naive(plan.next_run) > now_utc:
        return to_utc_naive(plan.next_run)
    if not plan.cron_expression:
        return None

    try:
        return calculate_next_cron_run(
            plan.cron_expression,
            now_utc,
            plan.timezone or DEFAULT_SCHEDULE_TIMEZONE,
        )
    except Exception:
        return None


# Pydantic models for responses
class SystemMetrics(BaseModel):
    cpu_usage: float
    cpu_count: int
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
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE
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


def promote_repository_health(
    health_status: str, health_color: str, severity: str
) -> tuple[str, str]:
    if severity == "critical":
        return "critical", "error"
    if severity == "warning" and health_status != "critical":
        return "warning", "warning"
    return health_status, health_color


def classify_day_age(days: int, warning_days: int, critical_days: int) -> str:
    if days > critical_days:
        return "critical"
    if days > warning_days:
        return "warning"
    return "healthy"


# A restore check row, as the facade over its `operations` row.
LatestRestoreCheck = MaintenanceJobFacade


def build_restore_check_health(
    repo: Repository,
    now: datetime,
    latest_restore_check: Optional[LatestRestoreCheck] = None,
    thresholds: Optional[DashboardHealthThresholds] = None,
    last_verdict: Optional[LatestRestoreCheck] = None,
) -> Dict[str, Any]:
    """Build restore-verification health without penalizing unconfigured repos.

    `latest_restore_check` is the newest row and drives the live status;
    `last_verdict` is the newest row that finished and drives the severity,
    so a run still queued or running does not hide the failure before it.
    Without it the newest row is the verdict when it has one."""
    thresholds = thresholds or DashboardHealthThresholds()
    # "Configured" requires both a cron expression AND the user-facing toggle
    # being on. Pausing via the toggle should not penalize dashboard health.
    schedule_enabled = getattr(repo, "restore_check_schedule_enabled", None)
    if schedule_enabled is None:
        schedule_enabled = True
    configured = bool(repo.restore_check_cron_expression) and bool(schedule_enabled)
    latest_status = latest_restore_check.status if latest_restore_check else None
    if last_verdict is None and latest_status not in UNSETTLED_STATUSES:
        last_verdict = latest_restore_check
    verdict_status = last_verdict.status if last_verdict else None
    verdict_error = last_verdict.error_message if last_verdict else None
    # An operation that did not run says why in its reason (spec 6.3); the
    # facade already reads the restore check's `needs_backup` back as such.
    verdict_reason = getattr(last_verdict, "skip_reason", None)
    # The live row rarely carries a message; the verdict's is what the
    # tooltip should show while a critical or warning reading stands.
    latest_error = (
        latest_restore_check.error_message if latest_restore_check else None
    ) or verdict_error
    last_success = repo.last_restore_check
    # The repository column is what the service stamps on success; the verdict
    # row is the same fact, so whichever is newer is the last success.
    if verdict_status == "completed" and last_verdict and last_verdict.completed_at:
        if not last_success or last_verdict.completed_at > last_success:
            last_success = last_verdict.completed_at

    if verdict_status == "failed":
        return {
            "dimension": "critical",
            "severity": "critical",
            "warning": f"Restore check failed: {verdict_error or 'unknown error'}",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if verdict_status == "completed_with_warnings":
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Restore check completed with warnings",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if verdict_status == "needs_backup":
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": verdict_error or "Restore check needs a backup first",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if verdict_status == "cancelled":
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Last restore check run was cancelled",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if verdict_status == "skipped":
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Restore check skipped"
            + (f": {verdict_reason.replace('_', ' ')}" if verdict_reason else ""),
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if latest_status in ("pending", "running") and not last_success:
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Restore check has not completed yet",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if last_success:
        days_since_restore_check = (now - last_success).days
        restore_dim = classify_day_age(
            days_since_restore_check,
            thresholds.restore_check_warning_days,
            thresholds.restore_check_critical_days,
        )
        if restore_dim == "critical":
            return {
                "dimension": "critical",
                "severity": "critical",
                "warning": f"No restore check in {days_since_restore_check} days",
                "configured": configured,
                "latest_status": latest_status,
                "latest_error": latest_error,
            }
        if restore_dim == "warning":
            return {
                "dimension": "warning",
                "severity": "warning",
                "warning": f"Last restore check {days_since_restore_check} days ago",
                "configured": configured,
                "latest_status": latest_status,
                "latest_error": latest_error,
            }
        return {
            "dimension": "healthy",
            "severity": None,
            "warning": None,
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    if configured:
        return {
            "dimension": "warning",
            "severity": "warning",
            "warning": "Restore check configured but never completed",
            "configured": configured,
            "latest_status": latest_status,
            "latest_error": latest_error,
        }

    return {
        "dimension": "unknown",
        "severity": None,
        "warning": None,
        "configured": configured,
        "latest_status": latest_status,
        "latest_error": latest_error,
    }


def build_full_repository_health(
    repo: Repository,
    now: datetime,
    latest_restore_check: Optional[LatestRestoreCheck] = None,
    thresholds: Optional[DashboardHealthThresholds] = None,
    last_verdict: Optional[LatestRestoreCheck] = None,
) -> Dict[str, Any]:
    """Build health signals for repositories managed directly by Borg UI."""
    thresholds = thresholds or DashboardHealthThresholds()
    health_status = "healthy"
    health_color = "success"
    warnings = []

    if repo.last_backup:
        days_since_backup = (now - repo.last_backup).days
        backup_dim = classify_day_age(
            days_since_backup,
            thresholds.backup_warning_days,
            thresholds.backup_critical_days,
        )
        if backup_dim == "critical":
            health_status = "critical"
            health_color = "error"
            warnings.append(f"No backup in {days_since_backup} days")
        elif backup_dim == "warning":
            health_status = "warning"
            health_color = "warning"
            warnings.append(f"Last backup {days_since_backup} days ago")
    else:
        health_status = "critical"
        health_color = "error"
        warnings.append("Never backed up")
        backup_dim = "critical"

    if repo.last_check:
        days_since_check = (now - repo.last_check).days
        check_dim = classify_day_age(
            days_since_check,
            thresholds.check_warning_days,
            thresholds.check_critical_days,
        )
    else:
        check_dim = "critical"

    if repo.last_compact:
        days_since_compact = (now - repo.last_compact).days
        compact_dim = classify_day_age(
            days_since_compact,
            thresholds.compact_warning_days,
            thresholds.compact_critical_days,
        )
    else:
        compact_dim = "critical"

    restore_check_health = build_restore_check_health(
        repo, now, latest_restore_check, thresholds, last_verdict=last_verdict
    )
    if restore_check_health["severity"]:
        health_status, health_color = promote_repository_health(
            health_status, health_color, restore_check_health["severity"]
        )
    if restore_check_health["warning"]:
        warnings.append(restore_check_health["warning"])

    return {
        "health_status": health_status,
        "health_color": health_color,
        "warnings": warnings,
        "restore_check_configured": restore_check_health["configured"],
        "latest_restore_check_status": restore_check_health["latest_status"],
        "latest_restore_check_error": restore_check_health["latest_error"],
        "dimension_health": {
            "backup": backup_dim,
            "check": check_dim,
            "compact": compact_dim,
            "restore": restore_check_health["dimension"],
        },
    }


def build_observe_repository_health(
    repo: Repository,
    now: datetime,
    latest_restore_check: Optional[LatestRestoreCheck] = None,
    thresholds: Optional[DashboardHealthThresholds] = None,
    last_verdict: Optional[LatestRestoreCheck] = None,
) -> Dict[str, Any]:
    """Build monitoring-oriented health signals for observe-only repositories."""
    thresholds = thresholds or DashboardHealthThresholds()
    freshness_dim = "healthy"
    check_dim = "unknown"
    archives_dim = "healthy"
    health_status = "healthy"
    health_color = "success"
    warnings = []

    if repo.archive_count and repo.archive_count > 0:
        archives_dim = "healthy"
    else:
        archives_dim = "critical"
        health_status = "critical"
        health_color = "error"
        warnings.append("No archives detected")

    if repo.last_backup:
        days_since_archive = (now - repo.last_backup).days
        freshness_dim = classify_day_age(
            days_since_archive,
            thresholds.observe_freshness_warning_days,
            thresholds.observe_freshness_critical_days,
        )
        if freshness_dim == "critical":
            freshness_dim = "critical"
            health_status = "critical"
            health_color = "error"
            warnings.append(f"No new archives in {days_since_archive} days")
        elif freshness_dim == "warning":
            if health_status != "critical":
                health_status = "warning"
                health_color = "warning"
            warnings.append(f"Latest archive {days_since_archive} days old")
    else:
        freshness_dim = "critical"
        health_status = "critical"
        health_color = "error"
        warnings.append("No archive freshness data available")

    if repo.last_check:
        days_since_check = (now - repo.last_check).days
        check_dim = classify_day_age(
            days_since_check,
            thresholds.check_warning_days,
            thresholds.check_critical_days,
        )
        if check_dim in ("critical", "warning") and health_status != "critical":
            health_status = "warning"
            health_color = "warning"

    restore_check_health = build_restore_check_health(
        repo, now, latest_restore_check, thresholds, last_verdict=last_verdict
    )
    if restore_check_health["severity"]:
        health_status, health_color = promote_repository_health(
            health_status, health_color, restore_check_health["severity"]
        )
    if restore_check_health["warning"]:
        warnings.append(restore_check_health["warning"])

    return {
        "health_status": health_status,
        "health_color": health_color,
        "warnings": warnings,
        "restore_check_configured": restore_check_health["configured"],
        "latest_restore_check_status": restore_check_health["latest_status"],
        "latest_restore_check_error": restore_check_health["latest_error"],
        "dimension_health": {
            # Reused as Freshness / Check / Archives on the frontend for observe-only repos.
            "backup": freshness_dim,
            "check": check_dim,
            "compact": archives_dim,
            "restore": restore_check_health["dimension"],
        },
    }


def build_backup_plan_summary(plans: list[BackupPlan], now: datetime) -> Dict[str, Any]:
    """Build repository-level backup plan counts and next scheduled run metadata."""
    scheduled_plans = [plan for plan in plans if plan.enabled and plan.schedule_enabled]
    scheduled_next_runs = [
        next_run
        for plan in scheduled_plans
        if (next_run := resolve_backup_plan_next_run(plan, now)) is not None
    ]
    return {
        "backup_plan_count": len(plans),
        "backup_plan_scheduled_count": len(scheduled_plans),
        "backup_plan_names": [plan.name for plan in plans],
        "backup_plan_next_run": serialize_datetime(
            min(scheduled_next_runs) if scheduled_next_runs else None
        ),
    }


def get_system_metrics() -> SystemMetrics:
    """Get system resource metrics"""
    try:
        try:
            cpu_usage = _cpu_sampler.read()
            cpu_count = psutil.cpu_count(logical=True) or 1
        except Exception as e:
            logger.warning("Failed to read CPU metrics", error=str(e))
            cpu_usage = 0.0
            cpu_count = 1

        try:
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            memory_total = memory.total
            memory_available = memory.available
        except Exception as e:
            logger.warning("Failed to read memory metrics", error=str(e))
            memory_usage = 0.0
            memory_total = 0
            memory_available = 0

        try:
            disk = psutil.disk_usage("/")
            disk_usage = disk.percent
            disk_total = disk.total
            disk_free = disk.free
        except Exception as e:
            logger.warning("Failed to read disk metrics", error=str(e))
            disk_usage = 0.0
            disk_total = 0
            disk_free = 0

        try:
            uptime = int(psutil.boot_time())
        except Exception as e:
            logger.warning("Failed to read system uptime", error=str(e))
            uptime = 0

        return SystemMetrics(
            cpu_usage=cpu_usage,
            cpu_count=cpu_count,
            memory_usage=memory_usage,
            memory_total=memory_total,
            memory_available=memory_available,
            disk_usage=disk_usage,
            disk_total=disk_total,
            disk_free=disk_free,
            uptime=uptime,
        )
    except Exception as e:
        logger.error("Failed to get system metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetSystemMetrics"},
        )


def get_scheduled_jobs(db: Session) -> List[ScheduledJobInfo]:
    """Get scheduled jobs information"""
    # TODO: Implement when ScheduledJob model is added back
    return []


def get_recent_jobs(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent backup jobs"""
    try:
        log_save_policy = get_log_save_policy(db)
        jobs = recent_backup_jobs(db, limit)
        job_list = []

        for job in jobs:
            # Determine trigger type
            triggered_by = "schedule" if job.scheduled_job_id else "manual"

            job_list.append(
                {
                    "id": job.id,
                    "repository": job.repository,
                    "status": job.status,
                    "started_at": format_datetime(job.started_at),
                    "completed_at": format_datetime(job.completed_at),
                    "progress": job.progress,
                    "error_message": job.error_message,
                    "triggered_by": triggered_by,
                    "schedule_id": job.scheduled_job_id,
                    "has_logs": job_has_logs_by_policy(
                        job,
                        log_save_policy,
                        output_text=[job.logs, job.error_message],
                        file_path=job.log_file_path,
                    ),
                }
            )

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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
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
            last_updated=format_datetime(datetime.utcnow()),
        )
    except Exception as e:
        logger.error("Error getting dashboard status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetDashboardStatus"},
        )


@router.get("/metrics", response_model=MetricsResponse)
async def get_dashboard_metrics(current_user: User = Depends(get_current_user)):
    """Get system metrics for dashboard"""
    try:
        # CPU usage, the shared non-blocking reading
        cpu_usage = _cpu_sampler.read()

        # Memory usage
        memory = psutil.virtual_memory()

        # Disk usage
        disk = psutil.disk_usage("/")

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
                "packets_recv": network.packets_recv,
            },
            load_average=list(load_avg),
        )
    except Exception as e:
        logger.error("Error getting metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetMetrics"},
        )


@router.get("/schedule", response_model=ScheduleResponse)
async def get_dashboard_schedule(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
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

        return ScheduleResponse(jobs=jobs, next_execution=next_execution)
    except Exception as e:
        logger.error("Error getting schedule", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.dashboard.failedGetSchedule"},
        )


ACTIVITY_KINDS = ("backup", "check", "compact", "prune", "restore_check")
ACTIVITY_LABELS = {
    "backup": "Backup",
    "check": "Check",
    "compact": "Compact",
    "prune": "Prune",
    "restore_check": "Restore check",
}
TIMELINE_DAYS = 14
TREND_WEEKS = 4
# a later run of these outcomes settles an earlier failure of the same kind
# on the same repository
RESOLVING_STATUSES = frozenset({"completed", "completed_with_warnings"})


def resolve_timezone(name: Optional[str]) -> tzinfo:
    """The zone the timeline buckets days in: the viewer's, or UTC for a name
    the host does not know (UTC without the zone database, which a host
    may lack)."""
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            # a key that names a directory of the zone database ("America")
            # raises IsADirectoryError rather than the not-found error
            pass
    return timezone.utc


def _feed_status(kind: str, status: Optional[str], skip_reason: Optional[str]) -> str:
    """The status word the feed always used: the facades' legacy vocabulary,
    with the restore check's "run a backup first" verdict as its own word."""
    if kind == "backup":
        return "pending" if status == "queued" else (status or "unknown")
    if status == "skipped" and skip_reason == NEEDS_BACKUP:
        return NEEDS_BACKUP
    return legacy_status(status or "unknown")


def _repository_name(
    repository_id: Optional[int],
    path: Optional[str],
    repo_id_map: dict,
    repo_name_map: dict,
) -> str:
    """The repository name for a feed entry: by id, then by the path the row
    captured (exact or without the trailing slash), then the path's last
    segment. The id wins over a captured path (the feed used to try the path
    first): a row with an id names the repository row, whatever path it had
    when the run started."""
    if repository_id and repository_id in repo_id_map:
        return repo_id_map[repository_id]
    if path in repo_name_map:
        return repo_name_map[path]
    if path and path.rstrip("/") in repo_name_map:
        return repo_name_map[path.rstrip("/")]
    return path.rstrip("/").split("/")[-1] if path else "Unknown"


def backup_run_counts(db: Session, now: datetime) -> list:
    """`(week, status, count)` over the backups started in the last 30 days,
    grouped in SQL. `week` is the trend bucket, 0 the oldest and 3 the last
    seven days; None for a run older than the four weeks but inside the 30
    days, which counts toward the success rate only."""
    week = case(
        # a run dated after now (a skewed clock) belongs to no week
        (Operation.started_at > now, None),
        (Operation.started_at >= now - timedelta(days=7), 3),
        (Operation.started_at >= now - timedelta(days=14), 2),
        (Operation.started_at >= now - timedelta(days=21), 1),
        (Operation.started_at >= now - timedelta(days=28), 0),
        else_=None,
    )
    return (
        db.query(week, Operation.status, func.count(Operation.id))
        .filter(
            Operation.kind == "backup",
            Operation.started_at >= now - timedelta(days=30),
        )
        .group_by(week, Operation.status)
        .all()
    )


def activity_rows(db: Session, since: datetime) -> list:
    """One row per operation of a feed kind started at or after `since`, the
    columns the timeline and the failure list read and nothing else; the
    error text only where a failure shows it."""
    return (
        db.query(
            Operation.id,
            Operation.kind,
            Operation.status,
            Operation.skip_reason,
            Operation.repository_id,
            Operation.started_at,
            case(
                (Operation.status == "failed", Operation.error_message), else_=None
            ).label("error_message"),
        )
        .filter(Operation.kind.in_(ACTIVITY_KINDS), Operation.started_at >= since)
        .all()
    )


def orphan_params(db: Session, since: datetime) -> dict:
    """`operations.params` by id for the window's rows whose repository the
    repository table does not know (no id, or a repository since deleted),
    limited to the statuses the failure list compares. One statement
    whatever the count: the rows are selected in the database, not by an
    id list."""
    unknown_repository = or_(
        Operation.repository_id.is_(None),
        ~exists().where(Repository.id == Operation.repository_id),
    )
    rows = (
        db.query(Operation.id, Operation.params)
        .filter(
            Operation.kind.in_(ACTIVITY_KINDS),
            Operation.started_at >= since,
            Operation.status.in_(("failed", *RESOLVING_STATUSES)),
            unknown_repository,
        )
        .all()
    )
    return {row_id: row_params or {} for row_id, row_params in rows}


def _local_date(value: datetime, zone: tzinfo) -> date:
    """The calendar day of a stored (naive UTC) timestamp in `zone`."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone).date()


def activity_timeline(rows, now: datetime, zone: tzinfo) -> list:
    """Per day and kind, how many runs started and how many of them failed,
    for the last TIMELINE_DAYS calendar days in `zone` (today included).
    That is what the timeline draws; the rows themselves stay on the server."""
    today = _local_date(now, zone)
    cells: dict[tuple[date, str], list[int]] = {}
    for row in rows:
        if row.started_at is None:
            continue
        day = _local_date(row.started_at, zone)
        age = (today - day).days
        if age < 0 or age >= TIMELINE_DAYS:
            continue
        cell = cells.setdefault((day, row.kind), [0, 0])
        cell[0] += 1
        if _feed_status(row.kind, row.status, row.skip_reason) == "failed":
            cell[1] += 1
    return [
        {"date": day.isoformat(), "type": kind, "total": total, "failed": failed}
        for (day, kind), (total, failed) in sorted(cells.items())
    ]


def current_failures(
    rows, params: dict, repo_id_map: dict, repo_name_map: dict, repo_path_map: dict
) -> list:
    """The failed runs among `rows` (the timeline window, as the page's own
    filter over the feed always saw it) that no later completed run of the
    same kind on the same repository has resolved, newest first, in the
    shape of a feed entry. Runs match by repository path, the row's own id
    resolved to the path it has now (`repo_path_map`) or the path a row
    without an id captured (`params`, from `orphan_params`); a row with
    neither resolves nothing and is resolved by nothing."""
    statuses = {
        row.id: _feed_status(row.kind, row.status, row.skip_reason) for row in rows
    }
    failed = [row for row in rows if statuses[row.id] == "failed"]
    if not failed:
        return []

    def path_of(row) -> Optional[str]:
        row_params = params.get(row.id, {})
        return row_params.get("repository_path") or row_params.get("repository")

    def key_of(row) -> tuple:
        if row.repository_id is not None:
            # a known repository by the path it has now; a deleted one by id,
            # so that its rows match each other whatever they captured
            path = repo_path_map.get(row.repository_id)
            if path:
                return (row.kind, "path", path.rstrip("/"))
            return (row.kind, "id", row.repository_id)
        path = path_of(row)
        if path:
            return (row.kind, "path", path.rstrip("/"))
        return (row.kind, "row", row.id)

    resolved_at: dict[tuple, datetime] = {}
    for row in rows:
        if statuses[row.id] in RESOLVING_STATUSES and row.started_at is not None:
            key = key_of(row)
            if key not in resolved_at or row.started_at > resolved_at[key]:
                resolved_at[key] = row.started_at
    entries = []
    for row in failed:
        name = _repository_name(
            row.repository_id, path_of(row), repo_id_map, repo_name_map
        )
        later = resolved_at.get(key_of(row))
        if later is not None and row.started_at is not None and later >= row.started_at:
            continue
        entries.append(
            {
                "id": row.id,
                "type": row.kind,
                "status": "failed",
                "repository": name,
                "timestamp": serialize_datetime(row.started_at),
                "message": f"{ACTIVITY_LABELS[row.kind]} failed",
                "error": row.error_message,
            }
        )
    entries.sort(
        key=lambda entry: (entry["timestamp"] or "", entry["id"]), reverse=True
    )
    return entries


@router.get("/overview")
def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    tz_name: Optional[str] = Query(default=None, alias="timezone"),
):
    """Get comprehensive dashboard overview with repository health, trends, and maintenance alerts.

    A plain `def`: the database work is synchronous and runs in the
    threadpool, so it does not hold the event loop for the other requests of
    the page."""
    try:
        now = datetime.utcnow()
        zone = resolve_timezone(tz_name)
        settings = db.query(SystemSettings).first()
        health_thresholds = DashboardHealthThresholds.from_settings(settings)

        # Get all repositories
        repositories = db.query(Repository).all()
        # Lookup maps for naming feed entries and schedules (paths stored
        # with and without a trailing slash)
        repo_name_map = {}
        repo_id_map = {}
        repo_path_map = {}
        for repo in repositories:
            repo_name_map[repo.path] = repo.name
            repo_name_map[repo.path.rstrip("/")] = repo.name
            repo_id_map[repo.id] = repo.name
            repo_path_map[repo.id] = repo.path

        # Separate full-mode repos (for health/maintenance) from observe-only repos
        full_mode_repos = [r for r in repositories if r.mode != "observe"]
        observe_only_repos = [r for r in repositories if r.mode == "observe"]

        # Get all schedules
        schedules = db.query(ScheduledJob).all()
        active_schedules = [s for s in schedules if s.enabled]

        # Get all backup plans so the dashboard can report the plan-native
        # automation counts separately from legacy schedules.
        backup_plans = db.query(BackupPlan).all()
        active_backup_plans = [p for p in backup_plans if p.enabled]
        backup_plan_links = (
            db.query(BackupPlanRepository, BackupPlan)
            .join(BackupPlan, BackupPlan.id == BackupPlanRepository.backup_plan_id)
            .filter(BackupPlanRepository.enabled.is_(True))
            .order_by(
                BackupPlanRepository.repository_id.asc(),
                BackupPlanRepository.execution_order.asc(),
                BackupPlan.name.asc(),
            )
            .all()
        )
        backup_plans_by_repo: dict[int, list[BackupPlan]] = {}
        for link, plan in backup_plan_links:
            backup_plans_by_repo.setdefault(link.repository_id, []).append(plan)

        # Get SSH connections
        ssh_connections = db.query(SSHConnection).all()

        # Multi-repository schedules, read once for every repository below
        schedule_repository_ids: dict[int, list[int]] = {}
        for scheduled_job_id, repository_id in db.query(
            ScheduledJobRepository.scheduled_job_id,
            ScheduledJobRepository.repository_id,
        ):
            schedule_repository_ids.setdefault(scheduled_job_id, []).append(
                repository_id
            )

        repository_ids = [repo.id for repo in repositories]
        latest_restore_checks = latest_maintenance_jobs_by_repository(
            db, "restore_check", repository_ids
        )
        restore_check_verdicts = latest_maintenance_jobs_by_repository(
            db, "restore_check", repository_ids, settled=True
        )

        # Calculate repository health (only for full-mode repos that do backups)
        repo_health = []
        total_size_bytes = 0
        total_archives = 0

        # Include all repos for size/archive totals
        for repo in repositories:
            size_bytes = repository_size_bytes(repo)
            total_size_bytes += size_bytes
            total_archives += repo.archive_count or 0

        # Show health for both repo modes, but with mode-specific semantics.
        for repo in full_mode_repos:
            # Parse size for this repo
            size_bytes = repository_size_bytes(repo)
            latest_restore_check = latest_restore_checks.get(repo.id)
            health = build_full_repository_health(
                repo,
                now,
                latest_restore_check,
                health_thresholds,
                last_verdict=restore_check_verdicts.get(repo.id),
            )

            # Get associated schedule — prefer enabled over disabled when multiple match
            repo_schedule = None
            fallback_schedule = None
            for schedule in schedules:
                matched = (
                    schedule.repository_id == repo.id
                    or repo.id in schedule_repository_ids.get(schedule.id, ())
                )
                if matched:
                    if schedule.enabled:
                        repo_schedule = schedule
                        break  # enabled match wins immediately
                    elif fallback_schedule is None:
                        fallback_schedule = schedule  # keep first disabled as fallback
            if repo_schedule is None:
                repo_schedule = fallback_schedule
            repo_backup_plans = backup_plans_by_repo.get(repo.id, [])

            repo_health.append(
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "type": repo.repository_type or "local",
                    "mode": repo.mode or "full",
                    "last_backup": serialize_datetime(repo.last_backup),
                    "last_check": serialize_datetime(repo.last_check),
                    "last_compact": serialize_datetime(repo.last_compact),
                    "last_restore_check": serialize_datetime(repo.last_restore_check),
                    "archive_count": repo.archive_count or 0,
                    "total_size": repo.total_size,
                    "size_bytes": size_bytes,
                    "health_status": health["health_status"],
                    "health_color": health["health_color"],
                    "warnings": health["warnings"],
                    "restore_check_configured": health["restore_check_configured"],
                    "latest_restore_check_status": health[
                        "latest_restore_check_status"
                    ],
                    "latest_restore_check_error": health["latest_restore_check_error"],
                    # nothing stores a per-repository deduplicated size
                    "dedup_ratio": None,
                    "has_schedule": repo_schedule is not None,
                    "schedule_enabled": repo_schedule.enabled
                    if repo_schedule
                    else False,
                    "schedule_name": repo_schedule.name if repo_schedule else None,
                    "next_run": serialize_datetime(repo_schedule.next_run)
                    if (
                        repo_schedule
                        and repo_schedule.enabled
                        and repo_schedule.next_run
                    )
                    else None,
                    **build_backup_plan_summary(repo_backup_plans, now),
                    "dimension_health": health["dimension_health"],
                }
            )

        for repo in observe_only_repos:
            size_bytes = repository_size_bytes(repo)
            latest_restore_check = latest_restore_checks.get(repo.id)
            health = build_observe_repository_health(
                repo,
                now,
                latest_restore_check,
                health_thresholds,
                last_verdict=restore_check_verdicts.get(repo.id),
            )
            repo_backup_plans = backup_plans_by_repo.get(repo.id, [])

            repo_health.append(
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "type": repo.repository_type or "local",
                    "mode": repo.mode or "observe",
                    "last_backup": serialize_datetime(repo.last_backup),
                    "last_check": serialize_datetime(repo.last_check),
                    "last_compact": serialize_datetime(repo.last_compact),
                    "last_restore_check": serialize_datetime(repo.last_restore_check),
                    "archive_count": repo.archive_count or 0,
                    "total_size": repo.total_size,
                    "size_bytes": size_bytes,
                    "health_status": health["health_status"],
                    "health_color": health["health_color"],
                    "warnings": health["warnings"],
                    "restore_check_configured": health["restore_check_configured"],
                    "latest_restore_check_status": health[
                        "latest_restore_check_status"
                    ],
                    "latest_restore_check_error": health["latest_restore_check_error"],
                    "dedup_ratio": None,
                    "has_schedule": False,
                    "schedule_enabled": False,
                    "schedule_name": None,
                    "next_run": None,
                    **build_backup_plan_summary(repo_backup_plans, now),
                    "dimension_health": health["dimension_health"],
                }
            )

        # Backup success rate (last 30 days) and the weekly trend, counted
        # in the database; only terminal runs make up the rate
        week_counts: dict[int, dict[str, int]] = {
            week: {"total": 0, "successful": 0, "failed": 0}
            for week in range(TREND_WEEKS)
        }
        successful_jobs = 0
        failed_jobs = 0
        for week, job_status, count in backup_run_counts(db, now):
            if job_status == "completed":
                successful_jobs += count
            elif job_status == "failed":
                failed_jobs += count
            if week is None:
                continue
            week_counts[week]["total"] += count
            if job_status == "completed":
                week_counts[week]["successful"] += count
            elif job_status == "failed":
                week_counts[week]["failed"] += count
        total_jobs = successful_jobs + failed_jobs
        success_rate = (successful_jobs / total_jobs * 100) if total_jobs > 0 else 0

        backup_trends = []
        for week in range(TREND_WEEKS):
            counts = week_counts[week]
            week_rate = (
                (counts["successful"] / counts["total"] * 100)
                if counts["total"] > 0
                else 0
            )
            backup_trends.append(
                {
                    "week": f"Week {week + 1}",
                    "success_rate": round(week_rate, 1),
                    "successful": counts["successful"],
                    "failed": counts["failed"],
                    "total": counts["total"],
                }
            )

        # Get upcoming schedules (next 24 hours)
        end_time = now + timedelta(hours=24)
        upcoming_tasks = []
        for schedule in active_schedules:
            next_run_dt = resolve_schedule_next_run(schedule, now)
            if not next_run_dt or next_run_dt > end_time:
                continue

            # Repository names for this schedule, from the rows already loaded
            if schedule.repository_id:
                repo_names = [
                    name for name in (repo_id_map.get(schedule.repository_id),) if name
                ]
            else:
                repo_names = [
                    repo_id_map[repository_id]
                    for repository_id in schedule_repository_ids.get(schedule.id, ())
                    if repository_id in repo_id_map
                ]

            upcoming_tasks.append(
                {
                    "id": schedule.id,
                    "name": schedule.name,
                    "repositories": repo_names,
                    "cron": schedule.cron_expression,
                    "timezone": schedule.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                    "next_run": serialize_datetime(next_run_dt),
                }
            )

        upcoming_tasks.sort(key=lambda item: item["next_run"])
        upcoming_tasks = upcoming_tasks[:10]

        # Get maintenance alerts (only for full-mode repos - observe-only repos don't need maintenance)
        maintenance_alerts = []

        # Check repos needing maintenance
        for repo in full_mode_repos:
            if repo.last_check:
                days_since_check = (now - repo.last_check).days
                if days_since_check > health_thresholds.check_critical_days:
                    maintenance_alerts.append(
                        {
                            "type": "check_overdue",
                            "severity": "warning"
                            if days_since_check
                            < health_thresholds.check_critical_days * 2
                            else "error",
                            "repository": repo.name,
                            "repository_id": repo.id,
                            "message": f"Check overdue by {days_since_check} days",
                            "action": "schedule_check",
                        }
                    )
            else:
                maintenance_alerts.append(
                    {
                        "type": "check_never",
                        "severity": "warning",
                        "repository": repo.name,
                        "repository_id": repo.id,
                        "message": "Never checked",
                        "action": "schedule_check",
                    }
                )

            if repo.last_compact:
                days_since_compact = (now - repo.last_compact).days
                if days_since_compact > health_thresholds.compact_critical_days:
                    maintenance_alerts.append(
                        {
                            "type": "compact_recommended",
                            "severity": "info",
                            "repository": repo.name,
                            "repository_id": repo.id,
                            "message": f"Compact recommended ({days_since_compact}d ago)",
                            "action": "schedule_compact",
                        }
                    )
            else:
                maintenance_alerts.append(
                    {
                        "type": "compact_never",
                        "severity": "info",
                        "repository": repo.name,
                        "repository_id": repo.id,
                        "message": "Never compacted",
                        "action": "schedule_compact",
                    }
                )

        # Activity of the last 14 days: the timeline counts per day and kind,
        # and the failures nothing has resolved since. The rows stay here.
        fourteen_days_ago = now - timedelta(days=TIMELINE_DAYS)
        recent_rows = activity_rows(db, fourteen_days_ago)
        timeline = activity_timeline(recent_rows, now, zone)
        failures = current_failures(
            recent_rows,
            orphan_params(db, fourteen_days_ago),
            repo_id_map,
            repo_name_map,
            repo_path_map,
        )

        # Count SSH connections (active = status is "connected")
        ssh_active = len([c for c in ssh_connections if c.status == "connected"])
        ssh_total = len(ssh_connections)

        # Get system metrics
        system_metrics = get_system_metrics()

        from app.services.prune_compare import space_savings

        savings = space_savings(db, full_mode_repos)

        return {
            "summary": {
                "total_repositories": len(repositories),
                "local_repositories": len(
                    [r for r in repositories if r.repository_type == "local"]
                ),
                "ssh_repositories": len(
                    [r for r in repositories if r.repository_type == "ssh"]
                ),
                "active_schedules": len(active_schedules),
                "total_schedules": len(schedules),
                "active_backup_plans": len(active_backup_plans),
                "total_backup_plans": len(backup_plans),
                "active_automations": len(active_schedules) + len(active_backup_plans),
                "total_automations": len(schedules) + len(backup_plans),
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
                "breakdown": sorted(
                    [
                        {
                            "name": repo.name,
                            "size": repo.total_size,
                            "size_bytes": repository_size_bytes(repo),
                            "percentage": round(
                                (repository_size_bytes(repo) / total_size_bytes * 100),
                                1,
                            )
                            if total_size_bytes > 0
                            else 0,
                        }
                        for repo in repositories
                    ],
                    key=lambda x: x["size_bytes"],
                    reverse=True,
                ),
            },
            "repository_health": sorted(
                repo_health,
                # Bucket-aware sort:
                # 1. Status bucket (critical > warning > healthy) puts urgency on top.
                # 2. Within critical/warning: oldest last_backup first, because a
                #    longer-running failure is more urgent. None (never backed up)
                #    sorts first as the most urgent case.
                # 3. Within healthy: skip the urgency dimension. Healthy means "no
                #    action needed", so alphabetical-by-name is the predictable
                #    table-of-contents order users want for finding a repo by name.
                # 4. Case-insensitive name as the final tiebreaker.
                key=lambda x: (
                    0
                    if x["health_status"] == "critical"
                    else 1
                    if x["health_status"] == "warning"
                    else 2,
                    # Collapse the timestamp dimension to a constant for healthy
                    # repos so name alone decides order within the healthy bucket.
                    0
                    if x["health_status"] == "healthy"
                    else (0 if x["last_backup"] is None else 1),
                    "" if x["health_status"] == "healthy" else (x["last_backup"] or ""),
                    (x.get("name") or "").lower(),
                ),
            ),
            "backup_trends": backup_trends,
            "upcoming_tasks": upcoming_tasks,
            "space_savings": savings,
            "activity_timeline": timeline,
            "current_failures": failures,
            # For one release: the previous release's page, served by an older
            # server and pointed at this one as a remote backend, reads
            # `activity_feed` and would crash without it. The failures are
            # feed-shaped, so that page keeps its failure strip; its timeline
            # shows the failures only.
            "activity_feed": failures,
            "system_metrics": system_metrics.dict(),
            "last_updated": serialize_datetime(now),
        }

    except Exception as e:
        logger.error("Error getting dashboard overview", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard overview: {str(e)}",
        )


def repository_size_bytes(repo) -> int:
    """The repository's measured size in bytes, by the one rule every size
    reader applies (`storage_usage.stored_size_bytes`); 0 when unknown."""
    return stored_size_bytes(repo) or 0


def calculate_average_dedup(repositories: List[Repository]) -> int:
    """Calculate average deduplication ratio across repositories"""
    # This is a placeholder - would need actual dedup data from borg info
    # For now, return None to indicate we don't have this data
    return None
