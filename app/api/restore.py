from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import structlog
from typing import Any, List, Literal, Optional
import os  # noqa: F401
from datetime import datetime, timezone

from app.database.models import User, Repository
from app.database.database import get_db
from app.core.borg_router import BorgRouter
from app.core.security import (
    get_current_user,
    check_repo_access,
    require_repository_access_by_path,
)
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations.details import restore_details
from app.services.operations.enqueue import enqueue, wake_runner
from app.services.operations.restore_facade import (
    CANCELLED_BY_USER,
    CANCELLED_PROCESS_NOT_FOUND,
    list_restore_jobs,
    resolve_restore_job,
)
from app.services.operations.runner import operation_runner
from app.services.repository_executor import is_agent_executor
from app.services.restore_service import restore_service
from app.utils.datetime_utils import serialize_datetime
from app.utils.borg_env import (
    get_standard_ssh_opts,
    setup_borg_env,
    cleanup_temp_key_file,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
    resolve_repository_ssh_connection,
)  # Backward-compatible patch target for tests

logger = structlog.get_logger()
router = APIRouter()


def _get_restore_job_repository(
    db: Session, repository_path: Optional[str]
) -> Optional[Repository]:
    if not repository_path:
        return None
    return db.query(Repository).filter(Repository.path == repository_path).first()


def _restore_job_logs_visible(job: Any, log_save_policy: str) -> bool:
    return job_has_logs_by_policy(
        job,
        log_save_policy,
        output_text=[job.logs, job.error_message],
    )


def _build_repo_env(repo: Repository, db: Session):
    temp_key_file = resolve_repo_ssh_key_file(repo, db)
    ssh_opts = get_standard_ssh_opts(
        include_key_path=temp_key_file,
        connection=resolve_repository_ssh_connection(repo, db),
        db=db,
    )
    env = setup_borg_env(passphrase=repo.passphrase, ssh_opts=ssh_opts)
    return env, temp_key_file


class RestorePathMetadata(BaseModel):
    path: str
    type: Literal["file", "directory"]


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
    restore_layout: Literal["preserve_path", "contents_only"] = "preserve_path"
    path_metadata: List[RestorePathMetadata] = Field(default_factory=list)


def _restore_path_metadata_to_dict(item: RestorePathMetadata) -> dict:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item.dict()


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

        # Phase 7: the row is an operation (spec 6.1) with its restore columns
        # on the details row (spec 6.2). The runner dispatches it (spec 7.1);
        # this route spawns nothing of its own.
        operation = enqueue(
            db,
            "restore",
            repository_id=repository.id,
            trigger="manual",
            params={
                "archive_name": restore_request.archive,
                "paths": list(restore_request.paths),
                "restore_layout": restore_request.restore_layout,
                "path_metadata": [
                    _restore_path_metadata_to_dict(item)
                    for item in restore_request.path_metadata
                ],
            },
            triggered_by_user_id=current_user.id,
            execution_mode="agent" if is_agent_executor(repository) else "server",
            commit=False,
        )
        details = restore_details(db, operation)
        details.archive = restore_request.archive
        details.destination = restore_request.destination
        details.destination_type = restore_request.destination_type
        details.destination_connection_id = restore_request.destination_connection_id
        details.destination_hostname = destination_hostname
        details.repository_type = repository.repository_type
        db.commit()
        wake_runner()

        logger.info(
            "Restore job created",
            job_id=operation.id,
            user=current_user.username,
            execution_mode=execution_mode,
            restore_layout=restore_request.restore_layout,
        )

        return {
            "job_id": operation.id,
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


@router.get("/jobs")
async def get_restore_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Get all restore jobs (most recent first)"""
    try:
        jobs = list_restore_jobs(db, limit)
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

        log_save_policy = get_log_save_policy(db)
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
                    "logs": (
                        job.logs
                        if _restore_job_logs_visible(job, log_save_policy)
                        else None
                    ),
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
        job = resolve_restore_job(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.restore.restoreJobNotFound"},
            )
        repo = _get_restore_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "operator")
        log_save_policy = get_log_save_policy(db)

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
            "logs": job.logs
            if _restore_job_logs_visible(job, log_save_policy)
            else None,
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
        job = resolve_restore_job(db, job_id)
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

        # Order matters. The runner's flag has to be raised while the row is
        # still `running` (request_cancel refuses any other status), and it is
        # what makes the executor keep `cancelled` if the service writes
        # `failed` for the killed process a moment later (spec 7.7). A
        # pre-phase-7 row has no operation and no task; request_cancel
        # answers False for it and the legacy write below still applies.
        await operation_runner.request_cancel(job_id)
        process_killed = await restore_service.cancel_restore(job_id)

        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = (
            CANCELLED_BY_USER if process_killed else CANCELLED_PROCESS_NOT_FOUND
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
