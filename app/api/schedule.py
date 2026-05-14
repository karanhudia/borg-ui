from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any, NoReturn
from datetime import datetime, timedelta, timezone
import structlog
import asyncio

from app.database.database import get_db, SessionLocal
from app.database.models import (
    User,
    ScheduledJob,
    ScheduledJobRepository,
    BackupJob,
    CompactJob,
    PruneJob,
    Repository,
    Script,
    RepositoryScript,
    SystemSettings,
    BackupPlan,
    BackupPlanRepository,
)
from app.core.authorization import authorize_request
from app.core.borg_router import BorgRouter
from app.core.security import get_current_user, check_repo_access
from app.config import settings
from app.api.maintenance_jobs import create_started_maintenance_job
from app.services.notification_service import notification_service
from app.services.check_scheduler import run_due_scheduled_checks
from app.services.restore_check_scheduler import run_due_scheduled_restore_checks
from app.utils.datetime_utils import serialize_datetime
from app.utils.archive_names import build_archive_name
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    InvalidScheduleTimezone,
    calculate_next_cron_run,
    calculate_next_cron_runs,
    normalize_schedule_timezone,
    to_utc_naive,
)

logger = structlog.get_logger()
router = APIRouter(tags=["schedule"], dependencies=[Depends(authorize_request)])
_active_scheduled_backup_runs: set[str] = set()

# Pydantic models
from pydantic import BaseModel


class ScheduledJobCreate(BaseModel):
    name: str
    cron_expression: str
    timezone: Optional[str] = None
    repository: Optional[str] = None  # Legacy single-repo (by path)
    repository_id: Optional[int] = None  # Single-repo (by ID)
    repository_ids: Optional[List[int]] = None  # Multi-repo (list of repo IDs)
    enabled: bool = True
    description: Optional[str] = None
    archive_name_template: Optional[str] = (
        None  # Template for archive names (e.g., "{job_name}-{now}")
    )
    # Multi-repo settings
    run_repository_scripts: bool = (
        False  # Whether to run per-repository pre/post scripts
    )
    pre_backup_script_id: Optional[int] = None  # Schedule-level pre-backup script
    post_backup_script_id: Optional[int] = None  # Schedule-level post-backup script
    pre_backup_script_parameters: Optional[Dict[str, Any]] = (
        None  # Parameters for pre-backup script
    )
    post_backup_script_parameters: Optional[Dict[str, Any]] = (
        None  # Parameters for post-backup script
    )
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
    timezone: Optional[str] = None
    repository: Optional[str] = None  # Legacy single-repo (by path)
    repository_id: Optional[int] = None  # Single-repo (by ID)
    repository_ids: Optional[List[int]] = None  # Multi-repo (list of repo IDs)
    enabled: Optional[bool] = None
    description: Optional[str] = None
    archive_name_template: Optional[str] = (
        None  # Template for archive names (e.g., "{job_name}-{now}")
    )
    # Multi-repo settings
    run_repository_scripts: Optional[bool] = None
    pre_backup_script_id: Optional[int] = None
    post_backup_script_id: Optional[int] = None
    pre_backup_script_parameters: Optional[Dict[str, Any]] = (
        None  # Parameters for pre-backup script
    )
    post_backup_script_parameters: Optional[Dict[str, Any]] = (
        None  # Parameters for post-backup script
    )
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
    timezone: Optional[str] = None


def _calculate_next_schedule_run(
    cron_expression: str,
    base_time: Optional[datetime] = None,
    schedule_timezone: Optional[str] = None,
) -> datetime:
    return calculate_next_cron_run(cron_expression, base_time, schedule_timezone)


def _raise_invalid_schedule_timezone(exc: InvalidScheduleTimezone) -> NoReturn:
    raise HTTPException(
        status_code=400,
        detail={
            "key": "backend.errors.schedule.invalidTimezone",
            "params": {"error": str(exc)},
        },
    )


def _count_active_scheduled_backup_runs() -> int:
    return len(_active_scheduled_backup_runs)


def _get_scheduler_concurrency_limits(db: Session) -> tuple[int, int]:
    settings = db.query(SystemSettings).first()
    max_scheduled_backups = (
        settings.max_concurrent_scheduled_backups
        if settings and settings.max_concurrent_scheduled_backups is not None
        else 2
    )
    max_scheduled_checks = (
        settings.max_concurrent_scheduled_checks
        if settings and settings.max_concurrent_scheduled_checks is not None
        else 4
    )
    return max_scheduled_backups, max_scheduled_checks


def _track_scheduled_backup_task(task: asyncio.Task, run_key: str) -> None:
    _active_scheduled_backup_runs.add(run_key)

    def _cleanup(_task: asyncio.Task) -> None:
        _active_scheduled_backup_runs.discard(run_key)

    task.add_done_callback(_cleanup)


def _dedupe_repository_ids(repository_ids: Optional[List[int]]) -> List[int]:
    if not repository_ids:
        return []

    seen: set[int] = set()
    unique_repo_ids: List[int] = []
    for repo_id in repository_ids:
        if repo_id not in seen:
            seen.add(repo_id)
            unique_repo_ids.append(repo_id)
    return unique_repo_ids


def _ensure_schedule_repository_allowed(repo: Optional[Repository]) -> None:
    if repo and repo.mode == "observe":
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.schedule.observabilityOnlyRepo",
                "params": {"name": repo.name},
            },
        )


def _get_schedule_target_repositories(
    db: Session,
    repository_path: Optional[str],
    repository_id: Optional[int],
    repository_ids: Optional[List[int]],
) -> tuple[Optional[Repository], Optional[Repository], List[Repository], List[int]]:
    legacy_repo = None
    if repository_path:
        legacy_repo = (
            db.query(Repository).filter(Repository.path == repository_path).first()
        )
        _ensure_schedule_repository_allowed(legacy_repo)

    single_repo = None
    if repository_id:
        single_repo = (
            db.query(Repository).filter(Repository.id == repository_id).first()
        )
        if single_repo is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.schedule.repositoryNotFound",
                    "params": {"id": repository_id},
                },
            )
        _ensure_schedule_repository_allowed(single_repo)

    unique_repo_ids = _dedupe_repository_ids(repository_ids)
    multi_repos: List[Repository] = []
    for repo_id in unique_repo_ids:
        repo = db.query(Repository).filter_by(id=repo_id).first()
        if not repo:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.schedule.repositoryNotFound",
                    "params": {"id": repo_id},
                },
            )
        _ensure_schedule_repository_allowed(repo)
        multi_repos.append(repo)

    return legacy_repo, single_repo, multi_repos, unique_repo_ids


def _require_schedule_payload_access(
    db: Session,
    current_user: User,
    repository_path: Optional[str],
    repository_id: Optional[int],
    repository_ids: Optional[List[int]],
    required_role: str,
) -> tuple[Optional[Repository], Optional[Repository], List[Repository], List[int]]:
    legacy_repo, single_repo, multi_repos, unique_repo_ids = (
        _get_schedule_target_repositories(
            db,
            repository_path,
            repository_id,
            repository_ids,
        )
    )

    for repo in [legacy_repo, single_repo, *multi_repos]:
        if repo:
            check_repo_access(db, current_user, repo, required_role)

    return legacy_repo, single_repo, multi_repos, unique_repo_ids


def _get_schedule_repositories(db: Session, job: ScheduledJob) -> List[Repository]:
    repositories: List[Repository] = []
    seen_ids: set[int] = set()

    if job.repository_id:
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo and repo.id not in seen_ids:
            repositories.append(repo)
            seen_ids.add(repo.id)

    if job.repository:
        repo = db.query(Repository).filter(Repository.path == job.repository).first()
        if repo and repo.id not in seen_ids:
            repositories.append(repo)
            seen_ids.add(repo.id)

    repo_links = (
        db.query(ScheduledJobRepository)
        .filter_by(scheduled_job_id=job.id)
        .order_by(ScheduledJobRepository.execution_order)
        .all()
    )
    for link in repo_links:
        if link.repository_id in seen_ids:
            continue
        repo = db.query(Repository).filter(Repository.id == link.repository_id).first()
        if repo:
            repositories.append(repo)
            seen_ids.add(repo.id)

    return repositories


def _require_schedule_access(
    db: Session, current_user: User, job: ScheduledJob, required_role: str
) -> List[Repository]:
    repositories = _get_schedule_repositories(db, job)

    if not repositories and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"key": "backend.errors.auth.insufficientPermissions"},
        )

    for repo in repositories:
        check_repo_access(db, current_user, repo, required_role)

    return repositories


def _get_backup_plan_repositories(plan: BackupPlan) -> List[Repository]:
    repositories = []
    for link in sorted(plan.repositories, key=lambda item: item.execution_order):
        if link.enabled and link.repository:
            repositories.append(link.repository)
    return repositories


def _require_backup_plan_schedule_access(
    db: Session, current_user: User, plan: BackupPlan, required_role: str
) -> List[Repository]:
    repositories = _get_backup_plan_repositories(plan)

    if not repositories and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"key": "backend.errors.auth.insufficientPermissions"},
        )

    for repo in repositories:
        check_repo_access(db, current_user, repo, required_role)

    return repositories


def _resolve_backup_plan_next_run(
    plan: BackupPlan, now: datetime
) -> Optional[datetime]:
    now_utc = to_utc_naive(now)
    if plan.next_run and to_utc_naive(plan.next_run) > now_utc:
        return to_utc_naive(plan.next_run)
    if not plan.cron_expression:
        return None
    try:
        return _calculate_next_schedule_run(
            plan.cron_expression,
            now_utc,
            plan.timezone or DEFAULT_SCHEDULE_TIMEZONE,
        )
    except Exception:
        return None


@router.get("/")
async def get_scheduled_jobs(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all scheduled jobs"""
    try:
        jobs = db.query(ScheduledJob).all()
        result_jobs = []

        for job in jobs:
            try:
                _require_schedule_access(db, current_user, job, "viewer")
            except HTTPException:
                continue
            # Get repository_ids from junction table
            repo_links = (
                db.query(ScheduledJobRepository)
                .filter_by(scheduled_job_id=job.id)
                .order_by(ScheduledJobRepository.execution_order)
                .all()
            )

            # Deduplicate repository IDs while preserving order (in case of database corruption)
            if repo_links:
                seen = set()
                repository_ids = []
                for link in repo_links:
                    if link.repository_id not in seen:
                        seen.add(link.repository_id)
                        repository_ids.append(link.repository_id)

                # Log if duplicates were found in database
                if len(repository_ids) != len(repo_links):
                    logger.warning(
                        "Found duplicate repository IDs in junction table",
                        schedule_id=job.id,
                        total_links=len(repo_links),
                        unique_repos=len(repository_ids),
                    )
            else:
                repository_ids = None

            result_jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "cron_expression": job.cron_expression,
                    "timezone": job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                    "repository": job.repository,
                    "repository_id": job.repository_id,
                    "repository_ids": repository_ids,
                    "enabled": job.enabled,
                    "last_run": serialize_datetime(job.last_run),
                    "next_run": serialize_datetime(job.next_run),
                    "created_at": serialize_datetime(job.created_at),
                    "updated_at": serialize_datetime(job.updated_at),
                    "description": job.description,
                    "archive_name_template": job.archive_name_template,
                    # Multi-repo settings
                    "run_repository_scripts": job.run_repository_scripts,
                    "pre_backup_script_id": job.pre_backup_script_id,
                    "post_backup_script_id": job.post_backup_script_id,
                    "pre_backup_script_parameters": job.pre_backup_script_parameters,
                    "post_backup_script_parameters": job.post_backup_script_parameters,
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
            )

        return {"success": True, "jobs": result_jobs}
    except Exception as e:
        logger.error("Failed to get scheduled jobs", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedRetrieveScheduledJobs",
                "params": {"error": str(e)},
            },
        )


@router.post("/")
async def create_scheduled_job(
    job_data: ScheduledJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new scheduled job"""
    try:
        _, _, _, unique_repo_ids = _require_schedule_payload_access(
            db,
            current_user,
            job_data.repository,
            job_data.repository_id,
            job_data.repository_ids,
            "operator",
        )
        logger.info(
            "STEP 0: Schedule creation request received",
            job_name=job_data.name,
            user=current_user.username,
            repository_ids=job_data.repository_ids,
            repository_id=job_data.repository_id,
            repository=job_data.repository,
        )

        # Check for orphaned schedules (diagnostic)
        try:
            # Find schedules with no junction entries
            all_schedules = db.query(ScheduledJob).all()
            orphaned_schedules = []

            for sched in all_schedules:
                junction_count = (
                    db.query(ScheduledJobRepository)
                    .filter_by(scheduled_job_id=sched.id)
                    .count()
                )

                # Check if this is a multi-repo schedule (has repository_ids but no legacy fields)
                is_multi_repo = not sched.repository_id and not sched.repository

                if is_multi_repo and junction_count == 0:
                    orphaned_schedules.append(
                        {
                            "id": sched.id,
                            "name": sched.name,
                            "created_at": str(sched.created_at)
                            if hasattr(sched, "created_at")
                            else None,
                        }
                    )

            if orphaned_schedules:
                logger.warning(
                    "STEP 0.1: Found orphaned schedules in database",
                    count=len(orphaned_schedules),
                    orphaned=orphaned_schedules[:5],
                )  # Limit to first 5
            else:
                logger.info("STEP 0.1: No orphaned schedules found in database")

            # Check for orphaned junction entries (entries pointing to non-existent schedules)
            # AND clean them up immediately to prevent UNIQUE constraint errors
            all_junction_entries = db.query(ScheduledJobRepository).all()
            orphaned_junctions_objects = []  # Store actual objects for deletion
            orphaned_junctions_info = []  # Store info for logging

            for junction in all_junction_entries:
                schedule_exists = (
                    db.query(ScheduledJob)
                    .filter_by(id=junction.scheduled_job_id)
                    .first()
                )
                if not schedule_exists:
                    orphaned_junctions_objects.append(
                        junction
                    )  # Save object for deletion
                    orphaned_junctions_info.append(
                        {
                            "id": junction.id,
                            "scheduled_job_id": junction.scheduled_job_id,
                            "repository_id": junction.repository_id,
                            "execution_order": junction.execution_order,
                        }
                    )

            if orphaned_junctions_info:
                logger.error(
                    "STEP 0.2: Found orphaned junction entries (pointing to deleted schedules)",
                    count=len(orphaned_junctions_info),
                    orphaned=orphaned_junctions_info[:10],
                )  # Limit to first 10

                # STEP 0.3: Clean up orphans immediately (don't wait for migration)
                logger.warning(
                    "STEP 0.3: Cleaning up orphaned junction entries before creating schedule",
                    count=len(orphaned_junctions_objects),
                )

                for junction in orphaned_junctions_objects:
                    db.delete(junction)

                db.commit()
                logger.info(
                    "STEP 0.3: Orphaned junction entries cleaned up successfully"
                )
            else:
                logger.info("STEP 0.2: No orphaned junction entries found")

        except Exception as check_error:
            logger.warning(
                "STEP 0.4: Could not check/clean orphaned data", error=str(check_error)
            )
            # Continue anyway - the atomic transaction + rollback will protect us

        # Validate timezone and cron expression
        try:
            schedule_timezone = normalize_schedule_timezone(job_data.timezone)
            next_run = _calculate_next_schedule_run(
                job_data.cron_expression,
                schedule_timezone=schedule_timezone,
            )
        except InvalidScheduleTimezone as e:
            _raise_invalid_schedule_timezone(e)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.schedule.invalidCronExpression",
                    "params": {"error": str(e)},
                },
            )

        # Check if job name already exists
        existing_job = (
            db.query(ScheduledJob).filter(ScheduledJob.name == job_data.name).first()
        )
        if existing_job:
            raise HTTPException(
                status_code=400, detail={"key": "backend.errors.schedule.jobNameExists"}
            )

        if job_data.repository_ids:
            logger.info(
                "STEP 1: Received repository_ids from frontend",
                repository_ids=job_data.repository_ids,
                count=len(job_data.repository_ids),
                job_name=job_data.name,
            )

            # Log deduplication results
            if len(unique_repo_ids) != len(job_data.repository_ids):
                logger.warning(
                    "STEP 2: Removed duplicate repository IDs",
                    original=job_data.repository_ids,
                    cleaned=unique_repo_ids,
                    removed_count=len(job_data.repository_ids) - len(unique_repo_ids),
                )
            else:
                logger.info(
                    "STEP 2: No duplicates found, using all repository IDs",
                    unique_repo_ids=unique_repo_ids,
                )

        # Create scheduled job
        scheduled_job = ScheduledJob(
            name=job_data.name,
            cron_expression=job_data.cron_expression,
            timezone=schedule_timezone,
            repository=job_data.repository,  # Legacy
            repository_id=job_data.repository_id,  # Single-repo by ID
            enabled=job_data.enabled,
            next_run=next_run,
            description=job_data.description,
            archive_name_template=job_data.archive_name_template,
            # Multi-repo settings
            run_repository_scripts=job_data.run_repository_scripts,
            pre_backup_script_id=job_data.pre_backup_script_id,
            post_backup_script_id=job_data.post_backup_script_id,
            pre_backup_script_parameters=job_data.pre_backup_script_parameters,
            post_backup_script_parameters=job_data.post_backup_script_parameters,
            # Prune and compact settings
            run_prune_after=job_data.run_prune_after,
            run_compact_after=job_data.run_compact_after,
            prune_keep_hourly=job_data.prune_keep_hourly,
            prune_keep_daily=job_data.prune_keep_daily,
            prune_keep_weekly=job_data.prune_keep_weekly,
            prune_keep_monthly=job_data.prune_keep_monthly,
            prune_keep_quarterly=job_data.prune_keep_quarterly,
            prune_keep_yearly=job_data.prune_keep_yearly,
        )

        logger.info(
            "STEP 3: Adding ScheduledJob to database",
            job_name=job_data.name,
            repository_field=job_data.repository,
            repository_id_field=job_data.repository_id,
        )

        db.add(scheduled_job)
        db.flush()  # Assign ID without committing
        db.refresh(scheduled_job)

        logger.info(
            "STEP 4: ScheduledJob flushed (ID assigned, not committed yet)",
            schedule_id=scheduled_job.id,
            schedule_name=scheduled_job.name,
        )

        # Create junction table entries for multi-repo schedule with deduplicated list
        if unique_repo_ids:
            # Check if there are any existing junction entries for this schedule_id (shouldn't be any)
            existing_entries = (
                db.query(ScheduledJobRepository)
                .filter_by(scheduled_job_id=scheduled_job.id)
                .all()
            )

            if existing_entries:
                logger.error(
                    "STEP 5: UNEXPECTED - Found existing junction entries for newly created schedule!",
                    schedule_id=scheduled_job.id,
                    existing_count=len(existing_entries),
                    existing_entries=[
                        (e.repository_id, e.execution_order) for e in existing_entries
                    ],
                )
            else:
                logger.info(
                    "STEP 5: No existing junction entries (as expected)",
                    schedule_id=scheduled_job.id,
                )

            logger.info(
                "STEP 6: Creating junction table entries",
                schedule_id=scheduled_job.id,
                repository_ids=unique_repo_ids,
                count=len(unique_repo_ids),
            )
            for order, repo_id in enumerate(unique_repo_ids):
                logger.debug(
                    "STEP 6.%d: Creating junction entry",
                    order,
                    schedule_id=scheduled_job.id,
                    repository_id=repo_id,
                    execution_order=order,
                )

                repo_link = ScheduledJobRepository(
                    scheduled_job_id=scheduled_job.id,
                    repository_id=repo_id,
                    execution_order=order,
                )
                db.add(repo_link)

            # Check what's pending in the session before commit
            pending_entries = [
                obj for obj in db.new if isinstance(obj, ScheduledJobRepository)
            ]
            logger.info(
                "STEP 7: Junction entries in session before COMMIT",
                count=len(pending_entries),
                entries=[
                    (e.scheduled_job_id, e.repository_id, e.execution_order)
                    for e in pending_entries
                ],
            )

            # Commit everything together (schedule + junction entries) - atomic transaction
            db.commit()

            logger.info(
                "STEP 8: Schedule and junction entries committed successfully (ATOMIC COMMIT)",
                schedule_id=scheduled_job.id,
                repo_count=len(unique_repo_ids),
            )

            # Verify what was actually saved
            saved_entries = (
                db.query(ScheduledJobRepository)
                .filter_by(scheduled_job_id=scheduled_job.id)
                .all()
            )
            logger.info(
                "STEP 9: Verification - Junction entries in database after commit",
                schedule_id=scheduled_job.id,
                saved_count=len(saved_entries),
                saved_entries=[
                    (e.repository_id, e.execution_order) for e in saved_entries
                ],
            )
        else:
            # No multi-repo setup (legacy single-repo), commit now
            db.commit()
            logger.info(
                "STEP 5: Legacy single-repo schedule committed",
                schedule_id=scheduled_job.id,
            )

        logger.info(
            "Scheduled job created", name=job_data.name, user=current_user.username
        )

        return {
            "success": True,
            "message": "backend.success.schedule.scheduledJobCreated",
            "job": {
                "id": scheduled_job.id,
                "name": scheduled_job.name,
                "cron_expression": scheduled_job.cron_expression,
                "timezone": scheduled_job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                "repository": scheduled_job.repository,
                "enabled": scheduled_job.enabled,
                "next_run": serialize_datetime(scheduled_job.next_run),
            },
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        # Capture schedule_id BEFORE rollback (to avoid PendingRollbackError when accessing .id)
        schedule_id_for_logging = None
        try:
            if "scheduled_job" in locals() and hasattr(scheduled_job, "id"):
                schedule_id_for_logging = scheduled_job.id
        except:
            pass  # Ignore if we can't get the ID

        db.rollback()  # Rollback any partial changes
        error_msg = str(e)
        error_type = type(e).__name__

        # Comprehensive error logging
        logger.error(
            "ERROR: Failed to create scheduled job - rolled back transaction",
            error_type=error_type,
            error_msg=error_msg,
            job_name=job_data.name,
            received_repository_ids=job_data.repository_ids,
            unique_repository_ids=unique_repo_ids
            if "unique_repo_ids" in locals()
            else None,
            schedule_id=schedule_id_for_logging,
        )

        # Check for UNIQUE constraint error
        if "UNIQUE constraint failed" in error_msg:
            logger.error(
                "ERROR: UNIQUE constraint violation detected",
                full_error=error_msg,
                job_data=job_data.dict(),
            )

            # Note: Cannot query database after rollback (would cause PendingRollbackError)
            # The diagnostic logs in STEP 5 already show existing entries

            raise HTTPException(
                status_code=500,
                detail={
                    "key": "backend.errors.schedule.dbConstraintError",
                    "params": {"error": error_msg},
                },
            )

        logger.error("Failed to create scheduled job", error=error_msg)
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedCreateScheduledJob",
                "params": {"error": error_msg},
            },
        )


@router.get("/cron-presets")
async def get_cron_presets(current_user: User = Depends(get_current_user)):
    """Get common cron expression presets"""
    presets = [
        {
            "name": "Every Minute",
            "expression": "* * * * *",
            "description": "Run every minute",
        },
        {
            "name": "Every 5 Minutes",
            "expression": "*/5 * * * *",
            "description": "Run every 5 minutes",
        },
        {
            "name": "Every 15 Minutes",
            "expression": "*/15 * * * *",
            "description": "Run every 15 minutes",
        },
        {
            "name": "Every Hour",
            "expression": "0 * * * *",
            "description": "Run every hour",
        },
        {
            "name": "Every 6 Hours",
            "expression": "0 */6 * * *",
            "description": "Run every 6 hours",
        },
        {
            "name": "Daily at Midnight",
            "expression": "0 0 * * *",
            "description": "Run daily at midnight",
        },
        {
            "name": "Daily at 2 AM",
            "expression": "0 2 * * *",
            "description": "Run daily at 2 AM",
        },
        {
            "name": "Weekly on Sunday",
            "expression": "0 0 * * 0",
            "description": "Run weekly on Sunday at midnight",
        },
        {
            "name": "Monthly on 1st",
            "expression": "0 0 1 * *",
            "description": "Run monthly on the 1st at midnight",
        },
        {
            "name": "Weekdays at 9 AM",
            "expression": "0 9 * * 1-5",
            "description": "Run weekdays at 9 AM",
        },
        {
            "name": "Weekends at 6 AM",
            "expression": "0 6 * * 0,6",
            "description": "Run weekends at 6 AM",
        },
    ]

    return {"success": True, "presets": presets}


@router.get("/upcoming-jobs")
async def get_upcoming_jobs(
    hours: int = Query(24, description="Hours to look ahead"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get upcoming scheduled jobs"""
    try:
        jobs = db.query(ScheduledJob).filter(ScheduledJob.enabled == True).all()
        upcoming_jobs = []

        now = to_utc_naive(datetime.now(timezone.utc))
        end_time = now + timedelta(hours=hours)

        for job in jobs:
            try:
                _require_schedule_access(db, current_user, job, "viewer")
                next_run = _calculate_next_schedule_run(
                    job.cron_expression,
                    now,
                    job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                )

                if next_run <= end_time:
                    repo_links = (
                        db.query(ScheduledJobRepository)
                        .filter_by(scheduled_job_id=job.id)
                        .order_by(ScheduledJobRepository.execution_order)
                        .all()
                    )
                    repository_ids = [link.repository_id for link in repo_links]
                    upcoming_jobs.append(
                        {
                            "id": job.id,
                            "type": "schedule",
                            "name": job.name,
                            "repository": job.repository,
                            "repository_id": job.repository_id,
                            "repository_ids": repository_ids,
                            "next_run": serialize_datetime(next_run),
                            "cron_expression": job.cron_expression,
                            "timezone": job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                        }
                    )
            except:
                continue

        plans = (
            db.query(BackupPlan)
            .options(
                joinedload(BackupPlan.repositories).joinedload(
                    BackupPlanRepository.repository
                )
            )
            .filter(
                BackupPlan.enabled == True,
                BackupPlan.schedule_enabled == True,
            )
            .all()
        )
        for plan in plans:
            try:
                repositories = _require_backup_plan_schedule_access(
                    db, current_user, plan, "viewer"
                )
                next_run = _resolve_backup_plan_next_run(plan, now)
                if not next_run or next_run > end_time:
                    continue

                upcoming_jobs.append(
                    {
                        "id": plan.id,
                        "type": "backup_plan",
                        "name": plan.name,
                        "repository": None,
                        "repository_id": None,
                        "repository_ids": [repo.id for repo in repositories],
                        "next_run": serialize_datetime(next_run),
                        "cron_expression": plan.cron_expression,
                        "timezone": plan.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                    }
                )
            except Exception:
                continue

        # Sort by next run time
        upcoming_jobs.sort(key=lambda x: x["next_run"])

        return {"success": True, "upcoming_jobs": upcoming_jobs, "hours_ahead": hours}
    except Exception as e:
        logger.error("Failed to get upcoming jobs", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedGetUpcomingJobs",
                "params": {"error": str(e)},
            },
        )


@router.get("/{job_id}")
async def get_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get scheduled job details"""
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.schedule.scheduledJobNotFound"},
            )
        _require_schedule_access(db, current_user, job, "viewer")

        # Calculate next run times
        try:
            next_runs = [
                serialize_datetime(next_dt)
                for next_dt in calculate_next_cron_runs(
                    job.cron_expression,
                    count=5,
                    schedule_timezone=job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                )
            ]
        except:
            next_runs = []

        return {
            "success": True,
            "job": {
                "id": job.id,
                "name": job.name,
                "cron_expression": job.cron_expression,
                "timezone": job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
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
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get scheduled job", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedRetrieveScheduledJob",
                "params": {"error": str(e)},
            },
        )


@router.put("/{job_id}")
async def update_scheduled_job(
    job_id: int,
    job_data: ScheduledJobUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update scheduled job"""
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.schedule.scheduledJobNotFound"},
            )
        _require_schedule_access(db, current_user, job, "operator")

        _, _, _, unique_repo_ids = _require_schedule_payload_access(
            db,
            current_user,
            job_data.repository,
            job_data.repository_id,
            job_data.repository_ids,
            "operator",
        )

        # Update fields
        if job_data.name is not None:
            # Check if name already exists
            existing_job = (
                db.query(ScheduledJob)
                .filter(ScheduledJob.name == job_data.name, ScheduledJob.id != job_id)
                .first()
            )
            if existing_job:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.schedule.jobNameExists"},
                )
            job.name = job_data.name

        schedule_definition_changed = (
            job_data.cron_expression is not None
            or "timezone" in job_data.model_fields_set
        )
        if schedule_definition_changed:
            next_cron_expression = (
                job_data.cron_expression
                if job_data.cron_expression is not None
                else job.cron_expression
            )
            try:
                next_schedule_timezone = normalize_schedule_timezone(
                    job_data.timezone
                    if "timezone" in job_data.model_fields_set
                    else job.timezone
                )
                next_run = _calculate_next_schedule_run(
                    next_cron_expression,
                    schedule_timezone=next_schedule_timezone,
                )
            except InvalidScheduleTimezone as e:
                _raise_invalid_schedule_timezone(e)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.schedule.invalidCronExpression",
                        "params": {"error": str(e)},
                    },
                )

            job.cron_expression = next_cron_expression
            job.timezone = next_schedule_timezone
            job.next_run = next_run

        if job_data.repository is not None:
            job.repository = job_data.repository

        was_enabled = job.enabled

        if job_data.enabled is not None:
            job.enabled = job_data.enabled
            if job.enabled and not was_enabled and not schedule_definition_changed:
                try:
                    job.next_run = _calculate_next_schedule_run(
                        job.cron_expression,
                        schedule_timezone=job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                    )
                except InvalidScheduleTimezone as e:
                    _raise_invalid_schedule_timezone(e)
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.schedule.invalidCronExpression",
                            "params": {"error": str(e)},
                        },
                    )

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

        # Update multi-repo settings
        if job_data.repository_id is not None:
            job.repository_id = job_data.repository_id

        if job_data.run_repository_scripts is not None:
            job.run_repository_scripts = job_data.run_repository_scripts

        if "pre_backup_script_id" in job_data.model_fields_set:
            job.pre_backup_script_id = job_data.pre_backup_script_id

        if "post_backup_script_id" in job_data.model_fields_set:
            job.post_backup_script_id = job_data.post_backup_script_id

        if job_data.pre_backup_script_parameters is not None:
            job.pre_backup_script_parameters = job_data.pre_backup_script_parameters

        if job_data.post_backup_script_parameters is not None:
            job.post_backup_script_parameters = job_data.post_backup_script_parameters

        # Handle repository_ids update (multi-repo)
        if job_data.repository_ids is not None:
            # Log if duplicates were found
            if len(unique_repo_ids) != len(job_data.repository_ids):
                logger.warning(
                    "Removed duplicate repository IDs from request",
                    original=job_data.repository_ids,
                    cleaned=unique_repo_ids,
                )

            # Delete existing junction table entries
            db.query(ScheduledJobRepository).filter_by(scheduled_job_id=job_id).delete()

            # Create new junction table entries with deduplicated list
            for order, repo_id in enumerate(unique_repo_ids):
                repo_link = ScheduledJobRepository(
                    scheduled_job_id=job_id,
                    repository_id=repo_id,
                    execution_order=order,
                )
                db.add(repo_link)

            logger.info(
                "Updated multi-repo schedule",
                schedule_id=job_id,
                repo_count=len(unique_repo_ids),
            )

        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Scheduled job updated", job_id=job_id, user=current_user.username)

        return {
            "success": True,
            "message": "backend.success.schedule.scheduledJobUpdated",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()  # Rollback any partial changes
        logger.error(
            "Failed to update scheduled job - rolled back transaction", error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedUpdateScheduledJob",
                "params": {"error": str(e)},
            },
        )


@router.delete("/{job_id}")
async def delete_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete scheduled job (operator or admin only)"""
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.schedule.scheduledJobNotFound"},
            )
        _require_schedule_access(db, current_user, job, "operator")

        # Step 1: Set scheduled_job_id to NULL for all backup jobs linked to this schedule
        # This preserves backup history while breaking the link
        from app.database.models import BackupJob

        db.query(BackupJob).filter_by(scheduled_job_id=job_id).update(
            {"scheduled_job_id": None}, synchronize_session=False
        )

        # Step 2: Manually delete junction table entries
        # (CASCADE doesn't work if tables were created before foreign keys were enabled)
        db.query(ScheduledJobRepository).filter_by(scheduled_job_id=job_id).delete()

        # Step 3: Now delete the schedule
        db.delete(job)
        db.commit()

        logger.info("Scheduled job deleted", job_id=job_id, user=current_user.username)

        return {
            "success": True,
            "message": "backend.success.schedule.scheduledJobDeleted",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to delete scheduled job", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedDeleteScheduledJob",
                "params": {"error": str(e)},
            },
        )


@router.post("/{job_id}/toggle")
async def toggle_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle scheduled job enabled/disabled state"""
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.schedule.scheduledJobNotFound"},
            )
        _require_schedule_access(db, current_user, job, "operator")

        job.enabled = not job.enabled
        if job.enabled:
            try:
                job.next_run = _calculate_next_schedule_run(
                    job.cron_expression,
                    schedule_timezone=job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
                )
            except InvalidScheduleTimezone as e:
                _raise_invalid_schedule_timezone(e)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.schedule.invalidCronExpression",
                        "params": {"error": str(e)},
                    },
                )
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Scheduled job toggled",
            job_id=job_id,
            enabled=job.enabled,
            user=current_user.username,
        )

        message = (
            "backend.success.schedule.scheduledJobEnabled"
            if job.enabled
            else "backend.success.schedule.scheduledJobDisabled"
        )
        return {"success": True, "message": message, "enabled": job.enabled}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to toggle scheduled job", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedToggleScheduledJob",
                "params": {"error": str(e)},
            },
        )


@router.post("/{job_id}/duplicate")
async def duplicate_scheduled_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Duplicate a scheduled job with a new name"""
    try:
        # Get the original job
        original_job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not original_job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.schedule.scheduledJobNotFound"},
            )
        _require_schedule_access(db, current_user, original_job, "operator")

        # Generate a unique name for the copy
        base_name = f"Copy of {original_job.name}"
        new_name = base_name
        counter = 1

        while db.query(ScheduledJob).filter(ScheduledJob.name == new_name).first():
            counter += 1
            new_name = f"{base_name} ({counter})"

        # Calculate next run time from cron expression
        try:
            next_run = _calculate_next_schedule_run(
                original_job.cron_expression,
                schedule_timezone=original_job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
            )
        except InvalidScheduleTimezone as e:
            _raise_invalid_schedule_timezone(e)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.schedule.invalidCronExpression",
                    "params": {"error": str(e)},
                },
            )

        # Create the duplicate job
        duplicated_job = ScheduledJob(
            name=new_name,
            cron_expression=original_job.cron_expression,
            timezone=original_job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
            repository=original_job.repository,
            repository_id=original_job.repository_id,
            enabled=False,  # Disable by default
            next_run=next_run,
            description=original_job.description,
            archive_name_template=original_job.archive_name_template,
            run_repository_scripts=original_job.run_repository_scripts,
            pre_backup_script_id=original_job.pre_backup_script_id,
            post_backup_script_id=original_job.post_backup_script_id,
            run_prune_after=original_job.run_prune_after,
            run_compact_after=original_job.run_compact_after,
            prune_keep_hourly=original_job.prune_keep_hourly,
            prune_keep_daily=original_job.prune_keep_daily,
            prune_keep_weekly=original_job.prune_keep_weekly,
            prune_keep_monthly=original_job.prune_keep_monthly,
            prune_keep_quarterly=original_job.prune_keep_quarterly,
            prune_keep_yearly=original_job.prune_keep_yearly,
        )

        db.add(duplicated_job)
        db.flush()  # Assign ID without committing
        db.refresh(duplicated_job)

        # Copy multi-repo associations if they exist
        original_repo_links = (
            db.query(ScheduledJobRepository)
            .filter_by(scheduled_job_id=job_id)
            .order_by(ScheduledJobRepository.execution_order)
            .all()
        )

        if original_repo_links:
            # Deduplicate repository IDs while preserving order
            seen = set()
            unique_repo_links = []
            for link in original_repo_links:
                if link.repository_id not in seen:
                    seen.add(link.repository_id)
                    unique_repo_links.append(link)

            # Log if duplicates were found
            if len(unique_repo_links) != len(original_repo_links):
                logger.warning(
                    "Removed duplicate repository entries from original schedule",
                    original_job_id=job_id,
                    original_count=len(original_repo_links),
                    unique_count=len(unique_repo_links),
                    removed_count=len(original_repo_links) - len(unique_repo_links),
                )

            # Create junction entries with deduplicated list
            for order, link in enumerate(unique_repo_links):
                new_link = ScheduledJobRepository(
                    scheduled_job_id=duplicated_job.id,
                    repository_id=link.repository_id,
                    execution_order=order,  # Use sequential order
                )
                db.add(new_link)

            # Commit everything together (schedule + junction entries)
            db.commit()
            logger.info(
                "Duplicated multi-repo associations",
                original_job_id=job_id,
                new_job_id=duplicated_job.id,
                repo_count=len(unique_repo_links),
            )
        else:
            # No multi-repo associations (legacy single-repo), commit now
            db.commit()

        logger.info(
            "Scheduled job duplicated",
            original_job_id=job_id,
            new_job_id=duplicated_job.id,
            new_name=new_name,
            user=current_user.username,
        )

        return {
            "success": True,
            "message": "backend.success.schedule.scheduledJobDuplicated",
            "job": {
                "id": duplicated_job.id,
                "name": duplicated_job.name,
                "enabled": duplicated_job.enabled,
                "cron_expression": duplicated_job.cron_expression,
                "timezone": duplicated_job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
            },
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()  # Rollback any partial changes
        logger.error(
            "Failed to duplicate scheduled job - rolled back transaction", error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedDuplicateScheduledJob",
                "params": {"error": str(e)},
            },
        )


@router.post("/{job_id}/run-now")
async def run_scheduled_job_now(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run a scheduled job immediately"""
    try:
        from app.database.models import BackupJob, Repository

        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.schedule.scheduledJobNotFound"},
            )

        # Check if this is a multi-repo schedule or single-repo schedule
        repo_links = (
            db.query(ScheduledJobRepository).filter_by(scheduled_job_id=job.id).all()
        )
        _require_schedule_access(db, current_user, job, "operator")

        if repo_links:
            # Multi-repository schedule
            logger.info(
                "Running multi-repo schedule manually",
                job_id=job_id,
                repo_count=len(repo_links),
            )

            # Update last run time BEFORE starting task
            job.last_run = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

            # Pass job_id instead of job object to avoid session issues
            asyncio.create_task(execute_multi_repo_schedule_by_id(job_id))

            return {
                "message": "backend.success.schedule.scheduledJobStartedMulti",
                "status": "pending",
            }

        elif job.repository or job.repository_id:
            # Single-repository schedule (legacy or new format)
            # Get repository by path (legacy) or ID (new)
            if job.repository_id:
                repo = db.query(Repository).filter_by(id=job.repository_id).first()
            else:
                repo = (
                    db.query(Repository)
                    .filter(Repository.path == job.repository)
                    .first()
                )

            if not repo:
                raise HTTPException(
                    status_code=404,
                    detail={"key": "backend.errors.schedule.repositoryNotFound"},
                )

            # Create backup job record with scheduled_job_id
            backup_job = BackupJob(
                repository=repo.path,
                status="pending",
                scheduled_job_id=job.id,  # Link to scheduled job
                created_at=datetime.now(
                    timezone.utc
                ),  # Explicit timestamp to prevent NULL
            )
            db.add(backup_job)
            db.commit()
            db.refresh(backup_job)

            # Generate archive name
            _now = datetime.now()
            archive_name = build_archive_name(
                job_name=job.name,
                repo_name=repo.name,
                template=job.archive_name_template or None,
                timestamp=_now.strftime("%Y-%m-%dT%H:%M:%S"),
                date=_now.strftime("%Y-%m-%d"),
                time_str=_now.strftime("%H:%M:%S"),
                unix_timestamp=str(int(_now.timestamp())),
            )

            # Execute backup with optional prune/compact asynchronously (non-blocking)
            asyncio.create_task(
                execute_scheduled_backup_with_maintenance(
                    backup_job.id, repo.path, job.id, archive_name=archive_name
                )
            )

            # Update last run time
            job.last_run = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                "Scheduled job run manually",
                job_id=job_id,
                user=current_user.username,
                backup_job_id=backup_job.id,
            )

            return {
                "job_id": backup_job.id,
                "status": "pending",
                "message": "backend.success.schedule.scheduledJobStarted",
            }
        else:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.schedule.noRepositoriesConfigured"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to run scheduled job", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedRunScheduledJob",
                "params": {"error": str(e)},
            },
        )


@router.post("/validate-cron")
async def validate_cron_expression(
    cron_data: CronExpression, current_user: User = Depends(get_current_user)
):
    """Validate and preview cron expression"""
    try:
        # Build cron expression
        cron_expr = f"{cron_data.minute} {cron_data.hour} {cron_data.day_of_month} {cron_data.month} {cron_data.day_of_week}"

        # Validate timezone and cron expression
        try:
            schedule_timezone = normalize_schedule_timezone(cron_data.timezone)
            next_runs = [
                serialize_datetime(next_dt)
                for next_dt in calculate_next_cron_runs(
                    cron_expr,
                    count=10,
                    schedule_timezone=schedule_timezone,
                )
            ]
        except InvalidScheduleTimezone as e:
            return {
                "success": False,
                "error": str(e),
                "cron_expression": cron_expr,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Invalid cron expression: {str(e)}",
                "cron_expression": cron_expr,
            }

        return {
            "success": True,
            "cron_expression": cron_expr,
            "timezone": schedule_timezone,
            "next_runs": next_runs,
            # croniter does not provide a stable human-readable description API
            # across versions. Return a safe fallback instead of failing the endpoint.
            "description": cron_expr,
        }
    except Exception as e:
        logger.error("Failed to validate cron expression", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.schedule.failedValidateCronExpression",
                "params": {"error": str(e)},
            },
        )


# Background task to check and run scheduled jobs
async def run_script_from_library(
    script: Script,
    db: Session,
    job_id: int = None,
    repository: Optional[Repository] = None,
    hook_type: Optional[str] = None,
    backup_result: Optional[str] = None,
    script_parameters: Optional[Dict[str, str]] = None,
):
    """Execute a script from the library

    Args:
        script: Script object from database
        db: Database session
        job_id: Optional backup job ID for context
        repository: Optional repository for BORG_UI_ variables
        hook_type: Optional hook type ('pre-backup' or 'post-backup')
        backup_result: Optional backup result ('success', 'failure', 'warning')
        script_parameters: Optional parameter values for the script
    """
    from app.services.script_executor import execute_script
    from app.services.template_service import get_system_variables
    from app.utils.script_params import SYSTEM_VARIABLE_PREFIX
    from app.core.security import decrypt_secret
    from pathlib import Path
    import os
    import json

    try:
        logger.info(
            "Executing schedule script", script_id=script.id, script_name=script.name
        )

        # Read script content from file
        full_path = Path(settings.data_dir) / "scripts" / script.file_path
        if not full_path.exists():
            raise Exception(f"Script file not found: {script.file_path}")
        script_content = full_path.read_text()

        # Build environment with system variables
        script_env = os.environ.copy()

        # Add BORG_UI_ system variables if repository context is provided
        if repository or hook_type or backup_result or job_id:
            system_vars = get_system_variables(
                repository_id=repository.id if repository else None,
                repository_name=repository.name if repository else None,
                repository_path=repository.path if repository else None,
                backup_status=backup_result,
                hook_type=hook_type,
                job_id=job_id,
            )
            script_env.update(system_vars)
            logger.info(
                "Added system variables to schedule script environment",
                script_id=script.id,
                system_vars=list(system_vars.keys()),
            )

        # Add script parameters if provided (always apply defaults even when script_parameters is None)
        if script.parameters:
            try:
                parameters = json.loads(script.parameters)

                for param_def in parameters:
                    param_name = param_def["name"]

                    # Skip system variables - they're already set above
                    if param_name.startswith(SYSTEM_VARIABLE_PREFIX):
                        continue

                    param_type = param_def.get("type", "text")
                    default_value = param_def.get("default", "")

                    # Get value from script_parameters or use default
                    value = (script_parameters or {}).get(param_name, default_value)

                    # Decrypt password-type parameters
                    if param_type == "password" and value:
                        try:
                            value = decrypt_secret(value)
                        except Exception as e:
                            logger.error(
                                "Failed to decrypt password parameter",
                                param_name=param_name,
                                error=str(e),
                            )
                            raise

                    # Add to environment
                    script_env[param_name] = value or ""

                logger.info(
                    "Added script parameters to environment",
                    script_id=script.id,
                    param_count=len(parameters),
                )
            except Exception as e:
                logger.error(
                    "Failed to prepare script parameters",
                    script_id=script.id,
                    error=str(e),
                )
                raise

        # Execute script with environment
        result = await execute_script(
            script=script_content,
            timeout=float(script.timeout),
            env=script_env,
            context=f"schedule:{script.name}",
        )

        if not result.get("success"):
            raise Exception(
                f"Script {script.name} failed: {result.get('stderr', 'Unknown error')}"
            )

        return result
    except Exception as e:
        logger.error("Script execution failed", script_name=script.name, error=str(e))
        raise


async def execute_multi_repo_schedule_by_id(scheduled_job_id: int):
    """Execute a multi-repository scheduled backup by job ID

    This wrapper function creates its own database session to avoid
    DetachedInstanceError when called from async tasks.

    Args:
        scheduled_job_id: The ScheduledJob ID to execute
    """
    # Create new database session for this async task
    db = SessionLocal()
    try:
        # Load the scheduled job
        scheduled_job = (
            db.query(ScheduledJob).filter(ScheduledJob.id == scheduled_job_id).first()
        )
        if not scheduled_job:
            logger.error("Scheduled job not found", scheduled_job_id=scheduled_job_id)
            return

        # Execute the multi-repo schedule
        await execute_multi_repo_schedule(scheduled_job, db)
    finally:
        db.close()


async def execute_multi_repo_schedule(scheduled_job: ScheduledJob, db: Session):
    """Execute a multi-repository scheduled backup

    Args:
        scheduled_job: The ScheduledJob object
        db: Database session
    """
    from app.database.models import Repository, BackupJob
    from app.services.backup_service import backup_service

    logger.info(
        "Executing multi-repo schedule",
        schedule_id=scheduled_job.id,
        name=scheduled_job.name,
    )

    # Get all repositories for this schedule (ordered)
    repo_links = (
        db.query(ScheduledJobRepository)
        .filter_by(scheduled_job_id=scheduled_job.id)
        .order_by(ScheduledJobRepository.execution_order)
        .all()
    )

    if not repo_links:
        logger.error(
            "No repositories found for multi-repo schedule",
            schedule_id=scheduled_job.id,
        )
        return

    repositories = []
    for link in repo_links:
        repo = db.query(Repository).filter_by(id=link.repository_id).first()
        if repo:
            repositories.append(repo)
        else:
            logger.warning("Repository not found", repo_id=link.repository_id)

    if not repositories:
        logger.error(
            "No valid repositories found for schedule", schedule_id=scheduled_job.id
        )
        return

    # 1. Run schedule-level pre-backup script (ONCE)
    if scheduled_job.pre_backup_script_id:
        try:
            script = (
                db.query(Script)
                .filter_by(id=scheduled_job.pre_backup_script_id)
                .first()
            )
            if script:
                # Execute schedule-level pre-backup script with parameters
                result = await run_script_from_library(
                    script=script,
                    db=db,
                    hook_type="pre-backup",
                    script_parameters=scheduled_job.pre_backup_script_parameters,
                )
                logger.info(
                    "Pre-backup script completed",
                    script_name=script.name,
                    exit_code=result.get("exit_code"),
                    stdout=result.get("stdout"),
                    stderr=result.get("stderr"),
                )
            else:
                logger.warning(
                    "Pre-backup script not found",
                    script_id=scheduled_job.pre_backup_script_id,
                )
        except Exception as e:
            logger.error("Pre-backup script failed, aborting schedule", error=str(e))
            return  # Abort entire schedule if pre-backup script fails

    # 2. Execute backups for each repository sequentially
    backup_jobs = []

    # Generate timestamp once for this schedule execution (with milliseconds for uniqueness)
    now = datetime.now()
    timestamp_now = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[
        :-3
    ]  # Include milliseconds (3 digits)
    timestamp_date = now.strftime("%Y-%m-%d")
    timestamp_time = now.strftime("%H:%M:%S")
    timestamp_unix = str(int(now.timestamp() * 1000))  # Unix timestamp in milliseconds

    for repo in repositories:
        try:
            logger.info(
                "Starting backup for repository",
                repo_name=repo.name,
                repo_path=repo.path,
            )

            # Create backup job record
            backup_job = BackupJob(
                repository=repo.path,
                status="pending",
                scheduled_job_id=scheduled_job.id,
                created_at=datetime.now(
                    timezone.utc
                ),  # Explicit timestamp to prevent NULL
            )
            db.add(backup_job)
            db.commit()
            db.refresh(backup_job)
            backup_jobs.append(backup_job)

            # Generate archive name
            archive_name = build_archive_name(
                job_name=scheduled_job.name,
                repo_name=repo.name,
                template=scheduled_job.archive_name_template or None,
                timestamp=timestamp_now,
                date=timestamp_date,
                time_str=timestamp_time,
                unix_timestamp=timestamp_unix,
            )

            # Run repository-level pre-scripts if enabled
            if scheduled_job.run_repository_scripts:
                try:
                    from app.services.script_library_executor import (
                        ScriptLibraryExecutor,
                    )

                    # Check for library scripts first (newer system)
                    library_scripts = (
                        db.query(RepositoryScript)
                        .filter(
                            RepositoryScript.repository_id == repo.id,
                            RepositoryScript.hook_type == "pre-backup",
                            RepositoryScript.enabled == True,
                        )
                        .order_by(RepositoryScript.execution_order)
                        .all()
                    )

                    if library_scripts:
                        # Execute library scripts in order
                        for repo_script in library_scripts:
                            script = (
                                db.query(Script)
                                .filter_by(id=repo_script.script_id)
                                .first()
                            )
                            if script:
                                # Parse parameter values for this repository script
                                import json

                                param_values = (
                                    json.loads(repo_script.parameter_values)
                                    if repo_script.parameter_values
                                    else None
                                )

                                await run_script_from_library(
                                    script=script,
                                    db=db,
                                    job_id=backup_job.id,
                                    repository=repo,
                                    hook_type="pre-backup",
                                    script_parameters=param_values,
                                )
                                logger.info(
                                    "Repository library pre-script completed",
                                    repo_name=repo.name,
                                    script_name=script.name,
                                )
                    elif repo.pre_backup_script:
                        # Fall back to inline script (legacy)
                        executor = ScriptLibraryExecutor(db)
                        timeout = repo.pre_hook_timeout or 300
                        result = await executor.execute_inline_script(
                            script_content=repo.pre_backup_script,
                            script_type="pre-backup",
                            timeout=timeout,
                            repository=repo,
                            backup_job_id=backup_job.id,
                            backup_result=None,
                        )
                        if result["success"]:
                            logger.info(
                                "Repository inline pre-script completed",
                                repo_name=repo.name,
                            )
                        else:
                            logger.error(
                                "Repository inline pre-script failed",
                                repo_name=repo.name,
                                error=result.get("logs"),
                            )
                except Exception as e:
                    logger.error(
                        "Repository pre-script failed",
                        repo_name=repo.name,
                        error=str(e),
                    )
                    # Continue with backup even if repo pre-script fails

            # Execute backup.
            # When run_repository_scripts=True the schedule already ran pre-backup scripts
            # explicitly above, so tell execute_backup to skip its own hook execution to
            # avoid running the same scripts a second time.
            await backup_service.execute_backup(
                backup_job.id,
                repo.path,
                db,
                archive_name=archive_name,
                skip_hooks=scheduled_job.run_repository_scripts,
            )

            # Run repository-level post-scripts if enabled
            if scheduled_job.run_repository_scripts:
                try:
                    from app.services.script_library_executor import (
                        ScriptLibraryExecutor,
                    )

                    # Get backup result for post-script context.
                    # Inline and library script executors expect the normalized
                    # status token, not a stats dict.
                    db.refresh(backup_job)
                    if backup_job.status == "completed":
                        result_status = "success"
                    elif backup_job.status == "completed_with_warnings":
                        result_status = "warning"
                    elif backup_job.status == "failed":
                        result_status = "failure"
                    else:
                        result_status = None

                    # Check for library scripts first (newer system)
                    library_scripts = (
                        db.query(RepositoryScript)
                        .filter(
                            RepositoryScript.repository_id == repo.id,
                            RepositoryScript.hook_type == "post-backup",
                            RepositoryScript.enabled == True,
                        )
                        .order_by(RepositoryScript.execution_order)
                        .all()
                    )

                    if library_scripts:
                        # Execute library scripts in order
                        for repo_script in library_scripts:
                            script = (
                                db.query(Script)
                                .filter_by(id=repo_script.script_id)
                                .first()
                            )
                            if script:
                                # Parse parameter values for this repository script
                                import json

                                param_values = (
                                    json.loads(repo_script.parameter_values)
                                    if repo_script.parameter_values
                                    else None
                                )

                                await run_script_from_library(
                                    script=script,
                                    db=db,
                                    job_id=backup_job.id,
                                    repository=repo,
                                    hook_type="post-backup",
                                    backup_result=result_status,
                                    script_parameters=param_values,
                                )
                                logger.info(
                                    "Repository library post-script completed",
                                    repo_name=repo.name,
                                    script_name=script.name,
                                )
                    elif repo.post_backup_script:
                        # Fall back to inline script (legacy)
                        executor = ScriptLibraryExecutor(db)
                        timeout = repo.post_hook_timeout or 300
                        result = await executor.execute_inline_script(
                            script_content=repo.post_backup_script,
                            script_type="post-backup",
                            timeout=timeout,
                            repository=repo,
                            backup_job_id=backup_job.id,
                            backup_result=result_status,
                        )
                        if result["success"]:
                            logger.info(
                                "Repository inline post-script completed",
                                repo_name=repo.name,
                            )
                        else:
                            logger.error(
                                "Repository inline post-script failed",
                                repo_name=repo.name,
                                error=result.get("logs"),
                            )
                except Exception as e:
                    logger.error(
                        "Repository post-script failed",
                        repo_name=repo.name,
                        error=str(e),
                    )

            # Run prune/compact if enabled and backup succeeded
            db.refresh(backup_job)
            if backup_job.status in ["completed", "completed_with_warnings"]:
                # Run prune if enabled
                if scheduled_job.run_prune_after:
                    prune_job = None
                    try:
                        logger.info("Running scheduled prune", repository=repo.path)
                        prune_job = create_started_maintenance_job(
                            db,
                            PruneJob,
                            repo,
                            extra_fields={"scheduled_prune": True},
                        )

                        # Update backup job status to show prune is running
                        backup_job.maintenance_status = "running_prune"
                        db.commit()

                        await BorgRouter(repo).prune(
                            job_id=prune_job.id,
                            keep_hourly=scheduled_job.prune_keep_hourly,
                            keep_daily=scheduled_job.prune_keep_daily,
                            keep_weekly=scheduled_job.prune_keep_weekly,
                            keep_monthly=scheduled_job.prune_keep_monthly,
                            keep_quarterly=scheduled_job.prune_keep_quarterly,
                            keep_yearly=scheduled_job.prune_keep_yearly,
                            dry_run=False,
                        )

                        # Refresh job to get updated status
                        db.refresh(prune_job)

                        if prune_job.status == "completed":
                            scheduled_job.last_prune = datetime.now(timezone.utc)
                            backup_job.maintenance_status = "prune_completed"
                            db.commit()
                            logger.info(
                                "Scheduled prune completed", repository=repo.path
                            )
                        else:
                            backup_job.maintenance_status = "prune_failed"
                            db.commit()
                            logger.error(
                                "Scheduled prune failed",
                                repository=repo.path,
                                error=prune_job.error_message,
                            )
                    except Exception as e:
                        # Ensure maintenance_status is always cleared even if commit fails
                        try:
                            backup_job.maintenance_status = "prune_failed"
                            # Update PruneJob record if it was created
                            if prune_job:
                                prune_job.status = "failed"
                                prune_job.completed_at = datetime.now(timezone.utc)
                                prune_job.error_message = str(e)
                            db.commit()
                        except Exception as commit_error:
                            logger.error(
                                "Failed to update prune status", error=str(commit_error)
                            )
                            # If commit fails, at least clear the running status in memory
                            backup_job.maintenance_status = None
                        logger.error(
                            "Scheduled prune failed", repository=repo.path, error=str(e)
                        )

                # Run compact if enabled
                if scheduled_job.run_compact_after:
                    try:
                        logger.info("Running scheduled compact", repository=repo.path)
                        compact_job = create_started_maintenance_job(
                            db,
                            CompactJob,
                            repo,
                            extra_fields={"scheduled_compact": True},
                        )

                        # Update backup job status to show compact is running
                        backup_job.maintenance_status = "running_compact"
                        db.commit()

                        await BorgRouter(repo).compact(compact_job.id)

                        # Refresh job to get updated status
                        db.refresh(compact_job)

                        if compact_job.status == "completed":
                            scheduled_job.last_compact = datetime.now(timezone.utc)
                            backup_job.maintenance_status = "compact_completed"
                            db.commit()
                            logger.info(
                                "Scheduled compact completed", repository=repo.path
                            )
                        else:
                            backup_job.maintenance_status = "compact_failed"
                            db.commit()
                            logger.error(
                                "Scheduled compact failed",
                                repository=repo.path,
                                error=compact_job.error_message,
                            )
                    except Exception as e:
                        backup_job.maintenance_status = "compact_failed"
                        # Update CompactJob record if it was created
                        try:
                            if "compact_job" in locals():
                                db.refresh(compact_job)
                                if compact_job.status not in [
                                    "failed",
                                    "cancelled",
                                    "completed",
                                ]:
                                    compact_job.status = "failed"
                                    compact_job.completed_at = datetime.now(
                                        timezone.utc
                                    )
                                    compact_job.error_message = str(e)
                        except:
                            pass
                        db.commit()
                        logger.error(
                            "Scheduled compact failed",
                            repository=repo.path,
                            error=str(e),
                        )

            logger.info(
                "Backup completed for repository",
                repo_name=repo.name,
                status=backup_job.status,
            )

        except Exception as e:
            logger.error(
                "Backup failed for repository", repo_name=repo.name, error=str(e)
            )
            # Continue with next repository even if this one fails

    # 3. Run schedule-level post-backup script (ONCE, always runs)
    if scheduled_job.post_backup_script_id:
        try:
            script = (
                db.query(Script)
                .filter_by(id=scheduled_job.post_backup_script_id)
                .first()
            )
            if script:
                # Execute schedule-level post-backup script with parameters
                result = await run_script_from_library(
                    script=script,
                    db=db,
                    hook_type="post-backup",
                    script_parameters=scheduled_job.post_backup_script_parameters,
                )
                logger.info(
                    "Post-backup script completed",
                    script_name=script.name,
                    exit_code=result.get("exit_code"),
                    stdout=result.get("stdout"),
                    stderr=result.get("stderr"),
                )
            else:
                logger.warning(
                    "Post-backup script not found",
                    script_id=scheduled_job.post_backup_script_id,
                )
        except Exception as e:
            logger.error("Post-backup script failed", error=str(e))
            # Post-script failure doesn't affect job completion

    logger.info(
        "Multi-repo schedule completed",
        schedule_id=scheduled_job.id,
        total_repos=len(repositories),
        completed_jobs=len(
            [
                j
                for j in backup_jobs
                if j.status in ["completed", "completed_with_warnings"]
            ]
        ),
    )


async def execute_scheduled_backup_with_maintenance(
    backup_job_id: int,
    repository_path: str,
    scheduled_job_id: int,
    archive_name: str = None,
):
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
        await backup_service.execute_backup(
            backup_job_id, repository_path, db, archive_name=archive_name
        )

        # Check if backup was successful (or completed with warnings)
        backup_job = db.query(BackupJob).filter(BackupJob.id == backup_job_id).first()
        if not backup_job or backup_job.status not in [
            "completed",
            "completed_with_warnings",
        ]:
            logger.info(
                "Backup did not complete successfully, skipping prune/compact",
                backup_job_id=backup_job_id,
                backup_status=backup_job.status if backup_job else "None",
            )
            return

        # Get scheduled job to check prune/compact settings
        scheduled_job = (
            db.query(ScheduledJob).filter(ScheduledJob.id == scheduled_job_id).first()
        )
        if not scheduled_job:
            return

        # Get repository info for prune/compact
        repo = db.query(Repository).filter(Repository.path == repository_path).first()
        if not repo:
            logger.error(
                "Repository not found for prune/compact", repository=repository_path
            )
            return

        # Run prune if enabled
        if scheduled_job.run_prune_after:
            prune_job = None
            try:
                logger.info(
                    "Running scheduled prune",
                    scheduled_job_id=scheduled_job_id,
                    repository=repository_path,
                )

                # Create a PruneJob record for tracking and activity feed
                prune_job = create_started_maintenance_job(
                    db,
                    PruneJob,
                    repo,
                    extra_fields={"scheduled_prune": True},
                )

                # Update backup job status to show prune is running
                backup_job.maintenance_status = "running_prune"
                db.commit()

                await BorgRouter(repo).prune(
                    job_id=prune_job.id,
                    keep_hourly=scheduled_job.prune_keep_hourly,
                    keep_daily=scheduled_job.prune_keep_daily,
                    keep_weekly=scheduled_job.prune_keep_weekly,
                    keep_monthly=scheduled_job.prune_keep_monthly,
                    keep_quarterly=scheduled_job.prune_keep_quarterly,
                    keep_yearly=scheduled_job.prune_keep_yearly,
                    dry_run=False,
                )

                # Refresh job to get updated status
                db.refresh(prune_job)

                if prune_job.status == "completed":
                    scheduled_job.last_prune = datetime.now(timezone.utc)
                    backup_job.maintenance_status = "prune_completed"
                    db.commit()
                    logger.info(
                        "Scheduled prune completed",
                        scheduled_job_id=scheduled_job_id,
                        prune_job_id=prune_job.id,
                    )
                else:
                    backup_job.maintenance_status = "prune_failed"
                    db.commit()
                    logger.error(
                        "Scheduled prune failed",
                        scheduled_job_id=scheduled_job_id,
                        prune_job_id=prune_job.id,
                        error=prune_job.error_message,
                    )

            except Exception as e:
                # Ensure maintenance_status is always cleared even if commit fails
                try:
                    backup_job.maintenance_status = "prune_failed"
                    # Update PruneJob record if it was created
                    if prune_job:
                        prune_job.status = "failed"
                        prune_job.completed_at = datetime.now(timezone.utc)
                        prune_job.error_message = str(e)
                    db.commit()
                except Exception as commit_error:
                    logger.error(
                        "Failed to update prune status", error=str(commit_error)
                    )
                    # If commit fails, at least clear the running status in memory
                    backup_job.maintenance_status = None
                logger.error(
                    "Failed to run scheduled prune",
                    scheduled_job_id=scheduled_job_id,
                    error=str(e),
                )

        # Run compact if enabled (only after successful prune or if prune not enabled)
        if scheduled_job.run_compact_after and (
            scheduled_job.run_prune_after or not scheduled_job.run_prune_after
        ):
            try:
                logger.info(
                    "Running scheduled compact",
                    scheduled_job_id=scheduled_job_id,
                    repository=repository_path,
                )

                # Create a CompactJob record for tracking and activity feed
                compact_job = create_started_maintenance_job(
                    db,
                    CompactJob,
                    repo,
                    extra_fields={"scheduled_compact": True},
                )

                # Update backup job status to show compact is running
                backup_job.maintenance_status = "running_compact"
                db.commit()

                await BorgRouter(repo).compact(compact_job.id)

                # Refresh job to get updated status
                db.refresh(compact_job)

                if compact_job.status == "completed":
                    scheduled_job.last_compact = datetime.now(timezone.utc)
                    backup_job.maintenance_status = "compact_completed"
                    db.commit()
                    logger.info(
                        "Scheduled compact completed",
                        scheduled_job_id=scheduled_job_id,
                        compact_job_id=compact_job.id,
                    )
                else:
                    backup_job.maintenance_status = "compact_failed"
                    db.commit()
                    logger.error(
                        "Scheduled compact failed",
                        scheduled_job_id=scheduled_job_id,
                        compact_job_id=compact_job.id,
                        error=compact_job.error_message,
                    )

            except Exception as e:
                backup_job.maintenance_status = "compact_failed"

                # Update CompactJob record if it was created
                try:
                    if "compact_job" in locals():
                        db.refresh(compact_job)
                        if compact_job.status not in [
                            "failed",
                            "cancelled",
                            "completed",
                        ]:
                            compact_job.status = "failed"
                            compact_job.completed_at = datetime.now(timezone.utc)
                            compact_job.error_message = str(e)
                except:
                    pass

                db.commit()
                logger.error(
                    "Failed to run scheduled compact",
                    scheduled_job_id=scheduled_job_id,
                    error=str(e),
                )

        # Mark maintenance as fully completed if we got this far
        if (
            backup_job.maintenance_status
            and "failed" not in backup_job.maintenance_status
        ):
            backup_job.maintenance_status = "maintenance_completed"
            db.commit()

    finally:
        db.close()


def _dispatch_due_scheduled_job(
    db: Session, job: ScheduledJob, now: datetime
) -> Optional[str]:
    """Dispatch one due scheduled backup job and return its runtime tracking key."""
    from app.database.models import Repository

    now = to_utc_naive(now)

    repo_links = (
        db.query(ScheduledJobRepository).filter_by(scheduled_job_id=job.id).all()
    )

    if repo_links:
        logger.info(
            "Dispatching multi-repo scheduled job",
            job_id=job.id,
            repo_count=len(repo_links),
        )
        run_key = f"schedule:{job.id}"
        task = asyncio.create_task(execute_multi_repo_schedule_by_id(job.id))
        _track_scheduled_backup_task(task, run_key)
    elif job.repository or job.repository_id:
        if job.repository_id:
            repo = db.query(Repository).filter_by(id=job.repository_id).first()
        else:
            repo = (
                db.query(Repository).filter(Repository.path == job.repository).first()
            )

        if not repo:
            logger.error(
                "Repository not found for scheduled job",
                job_id=job.id,
                repository=job.repository or job.repository_id,
            )
            return None

        backup_job = BackupJob(
            repository=repo.path,
            status="pending",
            scheduled_job_id=job.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(backup_job)
        db.commit()
        db.refresh(backup_job)

        _now = datetime.now()
        archive_name = build_archive_name(
            job_name=job.name,
            repo_name=repo.name,
            template=job.archive_name_template or None,
            timestamp=_now.strftime("%Y-%m-%dT%H:%M:%S"),
            date=_now.strftime("%Y-%m-%d"),
            time_str=_now.strftime("%H:%M:%S"),
            unix_timestamp=str(int(_now.timestamp())),
        )

        run_key = f"backup:{backup_job.id}"
        task = asyncio.create_task(
            execute_scheduled_backup_with_maintenance(
                backup_job.id,
                repo.path,
                job.id,
                archive_name=archive_name,
            )
        )
        _track_scheduled_backup_task(task, run_key)
    else:
        logger.error(
            "Scheduled job has no repositories configured",
            job_id=job.id,
        )
        return None

    job.last_run = now
    job.next_run = _calculate_next_schedule_run(
        job.cron_expression,
        now,
        job.timezone or DEFAULT_SCHEDULE_TIMEZONE,
    )
    db.commit()
    logger.info("Scheduled job started", job_id=job.id, name=job.name, run_key=run_key)
    return run_key


async def dispatch_due_scheduled_backups(
    db: Session, now: Optional[datetime] = None
) -> None:
    """Dispatch due scheduled backup jobs through the shared scheduler."""
    now = to_utc_naive(now or datetime.now(timezone.utc))
    max_scheduled_backups, _ = _get_scheduler_concurrency_limits(db)

    if max_scheduled_backups <= 0:
        logger.info("Scheduled backup dispatch disabled", limit=max_scheduled_backups)
        return

    active_runs = _count_active_scheduled_backup_runs()
    available_slots = max_scheduled_backups - active_runs
    if available_slots <= 0:
        logger.info(
            "Scheduled backup capacity reached",
            limit=max_scheduled_backups,
            active=active_runs,
        )
        return

    jobs = (
        db.query(ScheduledJob)
        .filter(
            ScheduledJob.enabled == True,
            ScheduledJob.next_run <= now,
        )
        .order_by(ScheduledJob.next_run.asc(), ScheduledJob.id.asc())
        .all()
    )

    if not jobs:
        return

    dispatched = 0
    for job in jobs:
        if dispatched >= available_slots:
            break
        try:
            run_key = _dispatch_due_scheduled_job(db, job, now)
            if run_key:
                dispatched += 1
        except Exception as e:
            logger.error("Failed to run scheduled job", job_id=job.id, error=str(e))
            job.last_run = now
            db.commit()

            try:
                asyncio.create_task(
                    notification_service.send_schedule_failure(
                        db, job.name, job.repository, str(e)
                    )
                )
            except Exception as notif_error:
                logger.warning(
                    "Failed to send schedule failure notification",
                    error=str(notif_error),
                )

    deferred = len(jobs) - dispatched
    if deferred > 0:
        logger.info(
            "Deferred due scheduled backups until capacity is available",
            deferred=deferred,
            dispatched=dispatched,
            limit=max_scheduled_backups,
        )


async def check_scheduled_jobs():
    """Check and execute scheduled backups and scheduled repository checks."""
    while True:
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            await dispatch_due_scheduled_backups(db, now)
            from app.services.backup_plan_execution_service import (
                backup_plan_execution_service,
            )

            backup_plan_execution_service.dispatch_due_runs(db, now)
            await run_due_scheduled_checks(db, now)
            await run_due_scheduled_restore_checks(db, now)

        except Exception as e:
            logger.error("Error in scheduled job checker", error=str(e))
        finally:
            db.close()

        # Wait for 1 minute before next check
        await asyncio.sleep(60)
