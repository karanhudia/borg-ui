from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse  # noqa: F401 - retained as a patch target in download endpoint tests
from sqlalchemy.orm import Session
import structlog
import json
import os
import tempfile  # noqa: F401 - retained as a patch target in download endpoint tests
from types import SimpleNamespace

from app.api.archive_download import extract_file_download
from app.database.database import get_db
from app.database.models import User, Repository, DeleteArchiveJob
from app.core.security import (
    get_current_user,
    get_current_download_user,
    check_repo_access,
    require_repository_access_by_path,
)
from app.core.borg import borg
from app.core.borg_router import BorgRouter
from app.utils.borg_env import (
    get_standard_ssh_opts,
    setup_borg_env,
    cleanup_temp_key_file,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
)  # Backward-compatible patch target for tests
import asyncio

logger = structlog.get_logger()
router = APIRouter()


def _build_repo_env(repo: Repository, db: Session):
    temp_key_file = resolve_repo_ssh_key_file(repo, db)
    ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file)
    env = setup_borg_env(passphrase=repo.passphrase, ssh_opts=ssh_opts)
    return env, temp_key_file


@router.get("/list")
async def list_archives(
    repository: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List archives in a repository"""
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        env, temp_key_file = _build_repo_env(repo, db)
        try:
            result = await borg.list_archives(
                repo.path,
                remote_path=repo.remote_path,
                passphrase=repo.passphrase,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
        finally:
            cleanup_temp_key_file(temp_key_file)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list archives: {result['stderr']}",
            )

        return {"archives": result["stdout"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list archives", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.archives.failedListArchives"},
        )


@router.get("/{archive_id}/info")
async def get_archive_info(
    repository: str,
    archive_id: str,
    include_files: bool = False,
    file_limit: int = 1000,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed information about a specific archive including command line, metadata, and optionally file listing"""
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        env, temp_key_file = _build_repo_env(repo, db)
        try:
            result = await borg.info_archive(
                repo.path,
                archive_id,
                remote_path=repo.remote_path,
                passphrase=repo.passphrase,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
        finally:
            cleanup_temp_key_file(temp_key_file)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive info: {result['stderr']}",
            )

        # Parse JSON output from Borg
        try:
            archive_data = json.loads(result["stdout"])

            # Extract archive information
            if "archives" in archive_data and len(archive_data["archives"]) > 0:
                archive_info = archive_data["archives"][0]
            else:
                archive_info = {}

            # Build enhanced response with all metadata
            enhanced_info = {
                "name": archive_info.get("name"),
                "id": archive_info.get("id"),
                "start": archive_info.get("start"),
                "end": archive_info.get("end"),
                "duration": archive_info.get("duration"),
                "stats": archive_info.get("stats", {}),
                # Creation metadata
                "command_line": archive_info.get("command_line", []),
                "hostname": archive_info.get("hostname"),
                "username": archive_info.get("username"),
                # Technical details
                "chunker_params": archive_info.get("chunker_params"),
                "limits": archive_info.get("limits", {}),
                "comment": archive_info.get("comment", ""),
                # Repository info
                "repository": archive_data.get("repository", {}),
                "encryption": archive_data.get("encryption", {}),
                "cache": archive_data.get("cache", {}),
            }

            # Optionally fetch file listing
            if include_files:
                env, temp_key_file = _build_repo_env(repo, db)
                try:
                    list_result = await borg.list_archive_contents(
                        repo.path,
                        archive_id,
                        remote_path=repo.remote_path,
                        passphrase=repo.passphrase,
                        bypass_lock=repo.bypass_lock,
                        env=env,
                    )
                finally:
                    cleanup_temp_key_file(temp_key_file)
                if list_result["success"]:
                    try:
                        # Parse JSON-lines output
                        files = []
                        for line in list_result["stdout"].strip().split("\n"):
                            if line and len(files) < file_limit:
                                try:
                                    file_obj = json.loads(line)
                                    files.append(
                                        {
                                            "path": file_obj.get("path"),
                                            "type": file_obj.get("type"),
                                            "mode": file_obj.get("mode"),
                                            "user": file_obj.get("user"),
                                            "group": file_obj.get("group"),
                                            "size": file_obj.get("size"),
                                            "mtime": file_obj.get("mtime"),
                                            "healthy": file_obj.get("healthy", True),
                                        }
                                    )
                                except json.JSONDecodeError:
                                    continue
                        enhanced_info["files"] = files
                        enhanced_info["file_count"] = len(files)
                    except Exception as e:
                        logger.warning("Failed to parse file listing", error=str(e))
                        enhanced_info["files"] = []
                        enhanced_info["file_count"] = 0
                else:
                    enhanced_info["files"] = []
                    enhanced_info["file_count"] = 0

            return {"info": enhanced_info}

        except json.JSONDecodeError:
            # Fallback to raw output if not JSON
            logger.warning("Archive info is not JSON, returning raw output")
            return {"info": result["stdout"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get archive info", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.archives.failedGetArchiveInfo"},
        )


@router.get("/{archive_id}/contents")
async def get_archive_contents(
    repository: str,
    archive_id: str,
    path: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get contents of an archive"""
    try:
        # Validate repository exists
        repo = require_repository_access_by_path(db, current_user, repository, "viewer")
        env, temp_key_file = _build_repo_env(repo, db)
        try:
            result = await borg.list_archive_contents(
                repo.path,
                archive_id,
                path,
                remote_path=repo.remote_path,
                passphrase=repo.passphrase,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
        finally:
            cleanup_temp_key_file(temp_key_file)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive contents: {result['stderr']}",
            )

        return {"contents": result["stdout"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get archive contents", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"key": "backend.errors.archives.failedGetArchiveContents"},
        )


@router.delete("/{archive_id}")
async def delete_archive(
    repository: str,
    archive_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an archive in the background (non-blocking)"""
    try:
        # Validate repository exists first
        repo = require_repository_access_by_path(
            db, current_user, repository, "operator"
        )
        # Check if there's already a running delete job for this archive
        running_job = (
            db.query(DeleteArchiveJob)
            .filter(
                DeleteArchiveJob.repository_id == repo.id,
                DeleteArchiveJob.archive_name == archive_id,
                DeleteArchiveJob.status == "running",
            )
            .first()
        )

        if running_job:
            raise HTTPException(
                status_code=409,
                detail={
                    "key": "backend.errors.archives.deleteAlreadyRunning",
                    "params": {"jobId": running_job.id},
                },
            )

        # Create delete job record
        delete_job = DeleteArchiveJob(
            repository_id=repo.id,
            repository_path=repo.path,
            archive_name=archive_id,
            status="pending",
        )
        db.add(delete_job)
        db.commit()
        db.refresh(delete_job)

        # Execute delete asynchronously (non-blocking)
        asyncio.create_task(
            BorgRouter(
                SimpleNamespace(id=repo.id, borg_version=repo.borg_version)
            ).delete_archive(delete_job.id, archive_id)
        )

        logger.info(
            "Delete archive job created",
            job_id=delete_job.id,
            repository_id=repo.id,
            archive=archive_id,
            user=current_user.username,
        )

        return {
            "job_id": delete_job.id,
            "status": "pending",
            "message": "backend.success.archives.deletionStarted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start delete archive job", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start archive deletion: {str(e)}",
        )


@router.get("/download")
async def download_file_from_archive(
    repository: str,
    archive: str,
    file_path: str,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    """Extract and download a specific file from an archive"""
    try:
        repo = require_repository_access_by_path(
            db,
            current_user,
            repository,
            "viewer",
            detail_key="backend.errors.archives.repositoryNotFound",
        )

        async def extract(temp_dir: str):
            env, temp_key_file = _build_repo_env(repo, db)
            try:
                return await borg.extract_archive(
                    repo.path,
                    archive,
                    [file_path],
                    temp_dir,
                    dry_run=False,
                    remote_path=repo.remote_path,
                    passphrase=repo.passphrase,
                    bypass_lock=repo.bypass_lock,
                    env=env,
                )
            finally:
                cleanup_temp_key_file(temp_key_file)

        return await extract_file_download(
            file_path,
            extract,
            temp_dir_factory=tempfile.mkdtemp,
            path_exists=os.path.exists,
            file_response_factory=FileResponse,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to download file from archive",
            repository=repository,
            archive=archive,
            file_path=file_path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}",
        )


# Delete job status endpoints
@router.get("/delete-jobs/{job_id}")
async def get_delete_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a delete archive job"""
    try:
        job = db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.archives.deleteJobNotFound"},
            )
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo:
            check_repo_access(db, current_user, repo, "viewer")

        # Read log file if it exists
        logs = None
        if job.log_file_path and os.path.exists(job.log_file_path):
            try:
                with open(job.log_file_path, "r") as f:
                    logs = f.read()
            except Exception as e:
                logger.warning("Failed to read delete log file", error=str(e))

        return {
            "id": job.id,
            "repository_id": job.repository_id,
            "archive_name": job.archive_name,
            "status": job.status,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "progress": job.progress,
            "progress_message": job.progress_message,
            "error_message": job.error_message,
            "logs": logs,
            "has_logs": job.has_logs,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get delete job status", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to get job status: {str(e)}"
        )


@router.post("/delete-jobs/{job_id}/cancel")
async def cancel_delete_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a running delete job"""
    try:
        job = db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.archives.deleteJobNotFound"},
            )
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo:
            check_repo_access(db, current_user, repo, "operator")
        await delete_archive_service.cancel_delete(job_id, db)
        return {"message": "backend.success.archives.deletionCancelled"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to cancel delete job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel delete job: {str(e)}"
        )
