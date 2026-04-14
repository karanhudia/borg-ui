from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
import structlog
from typing import List, Optional
import json
import os  # noqa: F401
from datetime import timezone
import asyncio

from app.database.models import User, Repository, RestoreJob
from app.database.database import get_db
from app.core.borg_router import BorgRouter
from app.core.security import (
    get_current_user,
    check_repo_access,
    require_repository_access_by_path,
)
from app.services.restore_service import restore_service
from app.services.archive_browse_service import build_browse_items, parse_archive_items
from app.services.cache_service import archive_cache
from app.services.v2.archive_browse import get_browse_depth, is_fast_browse_enabled
from app.utils.datetime_utils import serialize_datetime
from app.utils.borg_env import (
    get_standard_ssh_opts,
    setup_borg_env,
    cleanup_temp_key_file,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
)  # Backward-compatible patch target for tests

logger = structlog.get_logger()
router = APIRouter()


def _get_restore_job_repository(
    db: Session, repository_path: Optional[str]
) -> Optional[Repository]:
    if not repository_path:
        return None
    return db.query(Repository).filter(Repository.path == repository_path).first()


def _build_repo_env(repo: Repository, db: Session):
    temp_key_file = resolve_repo_ssh_key_file(repo, db)
    ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file)
    env = setup_borg_env(passphrase=repo.passphrase, ssh_opts=ssh_opts)
    return env, temp_key_file


def _get_restore_result_cache_key(archive_name: str, path: str, fast_v2: bool) -> str:
    normalized_path = path.strip("/")
    if fast_v2:
        if normalized_path:
            return f"{archive_name}::path::{normalized_path}::fast::result"
        return f"{archive_name}::fast::result"
    if not normalized_path:
        return f"{archive_name}::restore-root"
    return f"{archive_name}::restore::{normalized_path}"


def _get_restore_raw_cache_key(archive_name: str, path: str, fast_v2: bool) -> str:
    normalized_path = path.strip("/")
    if fast_v2:
        if normalized_path:
            return f"{archive_name}::path::{normalized_path}::fast::raw"
        return f"{archive_name}::fast::raw"
    return archive_name


class RestoreRequest(BaseModel):
    repository: str
    archive: str
    paths: List[str]
    destination: str
    dry_run: bool = False
    repository_id: int  # Repository ID for fetching repository details
    destination_type: str = "local"  # 'local' or 'ssh'
    destination_connection_id: Optional[int] = (
        None  # SSH connection ID for SSH destinations
    )


@router.post("/preview")
async def preview_restore(
    restore_request: RestoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview a restore operation"""
    try:
        # Get repository details for bypass_lock flag
        repo = require_repository_access_by_path(
            db,
            current_user,
            restore_request.repository,
            "viewer",
        )

        if (
            repo.repository_type == "ssh"
            or repo.path.startswith("ssh://")
            or repo.connection_id
        ):
            env, temp_key_file = _build_repo_env(repo, db)
            try:
                result = await BorgRouter(repo).preview_restore(
                    archive=restore_request.archive,
                    paths=restore_request.paths,
                    destination=restore_request.destination,
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)
        else:
            result = await BorgRouter(repo).preview_restore(
                archive=restore_request.archive,
                paths=restore_request.paths,
                destination=restore_request.destination,
            )
        return {"preview": result["stdout"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to preview restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedPreviewRestore"},
        )


@router.post("/start")
async def start_restore(
    restore_request: RestoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a restore operation and return job ID"""
    try:
        # Fetch repository to determine repository_type
        repository = (
            db.query(Repository)
            .filter(Repository.id == restore_request.repository_id)
            .first()
        )
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.restore.repositoryNotFound"},
            )
        check_repo_access(db, current_user, repository, "viewer")
        repository_path = repository.path

        # Validate scenario: SSH repository → SSH destination is not supported
        if (
            repository.repository_type == "ssh"
            and restore_request.destination_type == "ssh"
        ):
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.restore.sshToSshNotSupported"},
            )

        # Determine execution_mode based on repository_type + destination_type
        execution_mode = (
            f"{repository.repository_type}_to_{restore_request.destination_type}"
        )

        # Fetch destination hostname if SSH destination
        destination_hostname = None
        destination_connection = None
        if (
            restore_request.destination_type == "ssh"
            and restore_request.destination_connection_id
        ):
            from app.database.models import SSHConnection

            destination_connection = (
                db.query(SSHConnection)
                .filter(SSHConnection.id == restore_request.destination_connection_id)
                .first()
            )
            if destination_connection:
                destination_hostname = destination_connection.host

        # Create restore job record with new fields
        restore_job = RestoreJob(
            repository=repository_path,
            archive=restore_request.archive,
            destination=restore_request.destination,
            status="pending",
            destination_type=restore_request.destination_type,
            destination_connection_id=restore_request.destination_connection_id,
            execution_mode=execution_mode,
            destination_hostname=destination_hostname,
            repository_type=repository.repository_type,
        )
        db.add(restore_job)
        db.commit()
        db.refresh(restore_job)

        # Execute restore in background using asyncio.create_task
        # This ensures the task runs independently and doesn't block the response
        asyncio.create_task(
            restore_service.execute_restore(
                restore_job.id,
                repository_path,
                restore_request.archive,
                restore_request.destination,
                restore_request.paths,
                repository_type=repository.repository_type,
                destination_type=restore_request.destination_type,
                destination_connection_id=restore_request.destination_connection_id,
                ssh_connection_id=repository.connection_id
                if repository.repository_type == "ssh"
                else None,
            )
        )

        logger.info(
            "Restore job created",
            job_id=restore_job.id,
            user=current_user.username,
            execution_mode=execution_mode,
        )

        return {
            "job_id": restore_job.id,
            "status": "pending",
            "message": "backend.success.restore.restoreJobStarted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "key": "backend.errors.restore.failedStartRestore",
                "params": {"error": str(e)},
            },
        )


@router.get("/repositories")
async def get_repositories(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all repositories available for restore"""
    try:
        repositories = db.query(Repository).all()
        visible_repositories = []
        for repo in repositories:
            try:
                check_repo_access(db, current_user, repo, "viewer")
                visible_repositories.append(repo)
            except HTTPException:
                continue
        return {
            "repositories": [
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "repository_type": repo.repository_type,
                }
                for repo in visible_repositories
            ]
        }
    except Exception as e:
        logger.error("Failed to fetch repositories", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedFetchRepositories"},
        )


@router.get("/archives/{repository_id}")
async def get_archives(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all archives for a repository - delegates to repositories API"""
    try:
        # Use the existing repositories API implementation
        from app.api.repositories import list_repository_archives

        return await list_repository_archives(repository_id, current_user, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to fetch archives", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "key": "backend.errors.restore.failedFetchArchives",
                "params": {"error": str(e)},
            },
        )


@router.get("/contents/{repository_id}/{archive_name}")
async def get_archive_contents(
    repository_id: int,
    archive_name: str,
    path: str = Query("", description="Path within archive to browse"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get contents of an archive at a specific path"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.restore.repositoryNotFound"},
            )
        check_repo_access(db, current_user, repository, "viewer")
        fast_v2_browse = (repository.borg_version or 1) == 2 and is_fast_browse_enabled(
            db
        )
        normalized_path = path.lstrip("/") if path else ""
        result_cache_key = _get_restore_result_cache_key(
            archive_name, path, fast_v2_browse
        )
        raw_cache_key = _get_restore_raw_cache_key(archive_name, path, fast_v2_browse)

        cached_result = await archive_cache.get(repository_id, result_cache_key)
        if cached_result is not None:
            logger.info(
                "Using cached restore archive browse result",
                archive=archive_name,
                path=path,
                items_count=len(cached_result),
            )
            return {"items": cached_result}

        # Check cache first
        all_items = await archive_cache.get(repository_id, raw_cache_key)

        if all_items is not None:
            logger.info(
                "Using cached archive contents",
                archive=archive_name,
                items_count=len(all_items),
            )
        else:
            # Default browse fetches the whole archive for accurate recursive folder sizes.
            # Fast Borg2 browse fetches only the requested subtree and hides folder sizes.
            env, temp_key_file = _build_repo_env(repository, db)
            try:
                result = await BorgRouter(repository).list_archive_contents(
                    archive=archive_name,
                    path=path if fast_v2_browse else "",
                    browse_depth=get_browse_depth(repository, path)
                    if fast_v2_browse
                    else None,
                    env=env,
                )
            finally:
                try:
                    cleanup_temp_key_file(temp_key_file)
                except Exception:
                    pass

            # Parse all items
            all_items = []
            if result.get("stdout"):
                lines = result["stdout"].strip().split("\n")
                logger.info(
                    "Fetching and caching archive contents",
                    archive=archive_name,
                    total_lines=len(lines),
                )
                all_items = parse_archive_items(result["stdout"])

                # Store in cache
                await archive_cache.set(
                    repository_id,
                    raw_cache_key,
                    all_items,
                )
                logger.info(
                    "Cached archive contents",
                    archive=archive_name,
                    items_count=len(all_items),
                )

        items = build_browse_items(
            all_items,
            path,
            hide_directory_sizes=fast_v2_browse,
        )

        logger.info(
            "Archive contents parsed",
            archive=archive_name,
            path=path,
            items_count=len(items),
            first_few_items=[item["name"] for item in items[:10]],
        )

        await archive_cache.set(repository_id, result_cache_key, items)

        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to fetch archive contents",
            repository_id=repository_id,
            archive_name=archive_name,
            path=path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "key": "backend.errors.restore.failedFetchArchiveContents",
                "params": {"error": str(e)},
            },
        )


@router.get("/jobs")
async def get_restore_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Get all restore jobs (most recent first)"""
    try:
        jobs = db.query(RestoreJob).order_by(RestoreJob.id.desc()).limit(limit).all()
        visible_jobs = []
        for job in jobs:
            repo = _get_restore_job_repository(db, job.repository)
            if repo is None:
                if current_user.role == "admin":
                    visible_jobs.append(job)
                continue
            try:
                check_repo_access(db, current_user, repo, "viewer")
                visible_jobs.append(job)
            except HTTPException:
                continue

        return {
            "jobs": [
                {
                    "id": job.id,
                    "repository": job.repository,
                    "archive": job.archive,
                    "destination": job.destination,
                    "status": job.status,
                    "started_at": serialize_datetime(job.started_at),
                    "completed_at": serialize_datetime(job.completed_at),
                    "progress": job.progress,
                    "error_message": job.error_message,
                    "logs": job.logs,
                    "progress_details": {
                        "nfiles": job.nfiles or 0,
                        "current_file": job.current_file or "",
                        "progress_percent": job.progress_percent or 0.0,
                        "restore_speed": job.restore_speed or 0.0,
                        "estimated_time_remaining": job.estimated_time_remaining or 0,
                    },
                }
                for job in visible_jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get restore jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedGetRestoreJobs"},
        )


@router.get("/status/{job_id}")
async def get_restore_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get restore job status"""
    try:
        job = db.query(RestoreJob).filter(RestoreJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.restore.restoreJobNotFound"},
            )
        repo = _get_restore_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "operator")

        return {
            "id": job.id,
            "repository": job.repository,
            "archive": job.archive,
            "destination": job.destination,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "progress": job.progress,
            "error_message": job.error_message,
            "logs": job.logs,
            "progress_details": {
                "nfiles": job.nfiles or 0,
                "current_file": job.current_file or "",
                "progress_percent": job.progress_percent or 0.0,
                "restore_speed": job.restore_speed or 0.0,
                "estimated_time_remaining": job.estimated_time_remaining or 0,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get restore status", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedGetRestoreStatus"},
        )


@router.post("/cancel/{job_id}")
async def cancel_restore(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a running restore job"""
    try:
        job = db.query(RestoreJob).filter(RestoreJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.restore.restoreJobNotFound"},
            )
        repo = _get_restore_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "viewer")

        if job.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"key": "backend.errors.restore.canOnlyCancelRunningJobs"},
            )

        # Try to terminate the actual process
        from datetime import datetime

        process_killed = await restore_service.cancel_restore(job_id)

        # Update job status in database
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        if process_killed:
            job.error_message = json.dumps(
                {"key": "backend.errors.restore.cancelledByUser"}
            )
        else:
            job.error_message = json.dumps(
                {"key": "backend.errors.restore.cancelledByUserProcessNotFound"}
            )
        db.commit()

        logger.info(
            "Restore cancelled",
            job_id=job_id,
            user=current_user.username,
            process_killed=process_killed,
        )
        return {
            "message": "backend.success.restore.restoreCancelled",
            "process_terminated": process_killed,
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to cancel restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.restore.failedCancelRestore"},
        )
