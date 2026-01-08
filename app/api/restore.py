from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
import structlog
from typing import List, Optional
import json
from datetime import timezone
import asyncio

from app.database.models import User, Repository, RestoreJob
from app.database.database import get_db
from app.core.security import get_current_user
from app.core.borg import borg
from app.services.restore_service import restore_service
from app.services.cache_service import archive_cache
from app.utils.datetime_utils import serialize_datetime

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

        # Execute restore in background using asyncio.create_task
        # This ensures the task runs independently and doesn't block the response
        asyncio.create_task(
            restore_service.execute_restore(
                restore_job.id,
                restore_request.repository,
                restore_request.archive,
                restore_request.destination,
                restore_request.paths
            )
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

        # Check cache first
        all_items = await archive_cache.get(repository_id, archive_name)

        if all_items is not None:
            logger.info("Using cached archive contents",
                       archive=archive_name,
                       items_count=len(all_items))
        else:
            # If not in cache, fetch from borg (fetch ALL items, not just the requested path)
            result = await borg.list_archive_contents(
                repository.path,
                archive_name,
                path="",  # Always fetch all items for caching
                remote_path=repository.remote_path,
                passphrase=repository.passphrase
            )

            # Parse all items
            all_items = []
            if result.get("stdout"):
                lines = result["stdout"].strip().split("\n")
                logger.info("Fetching and caching archive contents",
                           archive=archive_name,
                           total_lines=len(lines))

                for line in lines:
                    if line:
                        try:
                            item_data = json.loads(line)
                            item_path = item_data.get("path", "")
                            if item_path:
                                all_items.append({
                                    "path": item_path,
                                    "type": item_data.get("type", ""),
                                    "size": item_data.get("size"),
                                })
                        except json.JSONDecodeError:
                            continue

                # Store in cache
                await archive_cache.set(repository_id, archive_name, all_items)
                logger.info("Cached archive contents",
                           archive=archive_name,
                           items_count=len(all_items))

        # Helper function to calculate directory size
        def calculate_directory_size(dir_path: str) -> int:
            """Calculate total size of all files in a directory recursively"""
            total_size = 0
            # Normalize the directory path
            norm_dir_path = dir_path.lstrip("/") if dir_path else ""
            search_prefix = f"{norm_dir_path}/" if norm_dir_path else ""

            for item in all_items:
                norm_item_path = item["path"].lstrip("/")
                # Check if this item is under the directory
                if search_prefix:
                    if norm_item_path.startswith(search_prefix) or norm_item_path == norm_dir_path:
                        # Only count files, not directories themselves
                        if item.get("type") != "d" and item.get("size") is not None:
                            total_size += item.get("size", 0)
                else:
                    # Root level - count all files
                    if item.get("type") != "d" and item.get("size") is not None:
                        total_size += item.get("size", 0)

            return total_size

        # Now filter the cached items for the requested path
        items = []
        seen_paths = set()

        for item in all_items:
            item_path = item["path"]
            item_type = item.get("type", "")
            item_size = item.get("size")

            # Skip empty paths
            if not item_path:
                continue

            # Normalize paths to handle potential leading slash mismatches
            # Some archives might store paths with leading slashes, others without
            norm_path = path.lstrip("/") if path else ""
            norm_item_path = item_path.lstrip("/")

            relative_path = ""

            if norm_path:
                # If browsing a subdirectory, only show items inside it
                if norm_item_path == norm_path:
                    # Skip the directory itself
                    continue
                elif norm_item_path.startswith(norm_path + "/"):
                    # It's a child item
                    relative_path = norm_item_path[len(norm_path) + 1:]
                else:
                    # Item is not inside the requested path
                    # This prevents the "phantom folder" bug where mismatched paths
                    # were treated as root-level items (e.g. showing "mnt" inside "/mnt/user/...")
                    continue
            else:
                # Root directory browsing
                relative_path = norm_item_path

            # Skip if empty
            if not relative_path:
                continue

            # Only show immediate children
            if "/" in relative_path:
                # This is a nested item, show only the directory
                dir_name = relative_path.split("/")[0]
                if dir_name not in seen_paths:
                    seen_paths.add(dir_name)
                    full_dir_path = f"{path}/{dir_name}" if path else dir_name
                    # Calculate directory size
                    dir_size = calculate_directory_size(full_dir_path)
                    items.append({
                        "name": dir_name,
                        "type": "directory",
                        "size": dir_size,
                        "path": full_dir_path
                    })
            else:
                # This is an immediate child
                if relative_path not in seen_paths:
                    seen_paths.add(relative_path)
                    full_path = f"{path}/{relative_path}" if path else relative_path

                    # For directories, calculate their size
                    if item_type == "d":
                        dir_size = calculate_directory_size(full_path)
                        items.append({
                            "name": relative_path,
                            "type": "directory",
                            "size": dir_size,
                            "path": full_path
                        })
                    else:
                        # For files, use the actual size
                        items.append({
                            "name": relative_path,
                            "type": "file",
                            "size": item_size,
                            "path": full_path
                        })

        # Sort: directories first, then by name
        items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        logger.info("Archive contents parsed",
                   archive=archive_name,
                   path=path,
                   items_count=len(items),
                   first_few_items=[item["name"] for item in items[:10]])

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
                    "started_at": serialize_datetime(job.started_at),
                    "completed_at": serialize_datetime(job.completed_at),
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
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
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

@router.post("/cancel/{job_id}")
async def cancel_restore(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a running restore job"""
    try:
        job = db.query(RestoreJob).filter(RestoreJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Restore job not found"
            )

        if job.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only cancel running jobs"
            )

        # Try to terminate the actual process
        from datetime import datetime
        process_killed = await restore_service.cancel_restore(job_id)

        # Update job status in database
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        if process_killed:
            job.error_message = "Restore cancelled by user"
        else:
            job.error_message = "Restore cancelled by user (process not found, may have already completed)"
        db.commit()

        logger.info("Restore cancelled", job_id=job_id, user=current_user.username, process_killed=process_killed)
        return {
            "message": "Restore cancelled successfully",
            "process_terminated": process_killed
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to cancel restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel restore"
        ) 