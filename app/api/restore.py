from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
import structlog
from typing import List, Optional
import json
from datetime import timezone

from app.database.models import User, Repository, RestoreJob
from app.database.database import get_db
from app.core.security import get_current_user
from app.core.borg import borg
from app.services.restore_service import restore_service

logger = structlog.get_logger()
router = APIRouter()

class RestoreRequest(BaseModel):
    repository: str
    archive: str
    paths: List[str]
    destination: str
    dry_run: bool = False

@router.post("/preview")
async def preview_restore(
    restore_request: RestoreRequest,
    current_user: User = Depends(get_current_user)
):
    """Preview a restore operation"""
    try:
        result = await borg.extract_archive(
            restore_request.repository,
            restore_request.archive,
            restore_request.paths,
            restore_request.destination,
            dry_run=True
        )
        return {"preview": result["stdout"]}
    except Exception as e:
        logger.error("Failed to preview restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to preview restore"
        )

@router.post("/start")
async def start_restore(
    restore_request: RestoreRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a restore operation and return job ID"""
    try:
        # Create restore job record
        restore_job = RestoreJob(
            repository=restore_request.repository,
            archive=restore_request.archive,
            destination=restore_request.destination,
            status="pending"
        )
        db.add(restore_job)
        db.commit()
        db.refresh(restore_job)

        # Execute restore in background
        background_tasks.add_task(
            restore_service.execute_restore,
            restore_job.id,
            restore_request.repository,
            restore_request.archive,
            restore_request.destination,
            restore_request.paths
        )

        logger.info("Restore job created", job_id=restore_job.id, user=current_user.username)

        return {
            "job_id": restore_job.id,
            "status": "pending",
            "message": "Restore job started"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start restore: {str(e)}"
        )

@router.get("/repositories")
async def get_repositories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all repositories available for restore"""
    try:
        repositories = db.query(Repository).all()
        return {
            "repositories": [
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "repository_type": repo.repository_type
                }
                for repo in repositories
            ]
        }
    except Exception as e:
        logger.error("Failed to fetch repositories", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch repositories"
        )

@router.get("/archives/{repository_id}")
async def get_archives(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all archives for a repository - delegates to repositories API"""
    try:
        # Use the existing repositories API implementation
        from app.api.repositories import list_repository_archives
        return await list_repository_archives(repository_id, current_user, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch archives", repository_id=repository_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch archives: {str(e)}"
        )

@router.get("/contents/{repository_id}/{archive_name}")
async def get_archive_contents(
    repository_id: int,
    archive_name: str,
    path: str = Query("", description="Path within archive to browse"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get contents of an archive at a specific path"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        result = await borg.list_archive_contents(
            repository.path,
            archive_name,
            path=path,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )

        # Parse borg list output
        items = []
        seen_paths = set()

        if result.get("stdout"):
            for line in result["stdout"].strip().split("\n"):
                if line:
                    try:
                        item_data = json.loads(line)
                        item_path = item_data.get("path", "")

                        # Skip empty paths
                        if not item_path:
                            continue

                        # Get relative path from current directory
                        if path and item_path.startswith(path + "/"):
                            relative_path = item_path[len(path) + 1:]
                        elif path and item_path == path:
                            continue
                        else:
                            relative_path = item_path

                        # Only show immediate children
                        if "/" in relative_path:
                            # This is a nested item, show only the directory
                            dir_name = relative_path.split("/")[0]
                            if dir_name not in seen_paths:
                                seen_paths.add(dir_name)
                                items.append({
                                    "name": dir_name,
                                    "type": "directory",
                                    "path": f"{path}/{dir_name}" if path else dir_name
                                })
                        else:
                            # This is an immediate child
                            if relative_path not in seen_paths:
                                seen_paths.add(relative_path)
                                item_type = item_data.get("type", "")
                                items.append({
                                    "name": relative_path,
                                    "type": "directory" if item_type == "d" else "file",
                                    "size": item_data.get("size"),
                                    "path": f"{path}/{relative_path}" if path else relative_path
                                })
                    except json.JSONDecodeError:
                        continue

        # Sort: directories first, then by name
        items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch archive contents", repository_id=repository_id,
                    archive_name=archive_name, path=path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch archive contents: {str(e)}"
        )

@router.get("/jobs")
async def get_restore_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50
):
    """Get all restore jobs (most recent first)"""
    try:
        jobs = db.query(RestoreJob).order_by(RestoreJob.id.desc()).limit(limit).all()

        return {
            "jobs": [
                {
                    "id": job.id,
                    "repository": job.repository,
                    "archive": job.archive,
                    "destination": job.destination,
                    "status": job.status,
                    "started_at": job.started_at.replace(tzinfo=timezone.utc).isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.replace(tzinfo=timezone.utc).isoformat() if job.completed_at else None,
                    "progress": job.progress,
                    "error_message": job.error_message,
                    "progress_details": {
                        "nfiles": job.nfiles or 0,
                        "current_file": job.current_file or "",
                        "progress_percent": job.progress_percent or 0.0,
                    }
                }
                for job in jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get restore jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get restore jobs"
        )

@router.get("/status/{job_id}")
async def get_restore_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get restore job status"""
    try:
        job = db.query(RestoreJob).filter(RestoreJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Restore job not found"
            )

        return {
            "id": job.id,
            "repository": job.repository,
            "archive": job.archive,
            "destination": job.destination,
            "status": job.status,
            "started_at": job.started_at.replace(tzinfo=timezone.utc).isoformat() if job.started_at else None,
            "completed_at": job.completed_at.replace(tzinfo=timezone.utc).isoformat() if job.completed_at else None,
            "progress": job.progress,
            "error_message": job.error_message,
            "logs": job.logs,
            "progress_details": {
                "nfiles": job.nfiles or 0,
                "current_file": job.current_file or "",
                "progress_percent": job.progress_percent or 0.0,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get restore status", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get restore status"
        ) 