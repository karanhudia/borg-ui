from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
import structlog
from typing import List, Optional
import json

from app.database.models import User, Repository
from app.database.database import get_db
from app.core.security import get_current_user
from app.core.borg import borg

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
    current_user: User = Depends(get_current_user)
):
    """Start a restore operation"""
    try:
        result = await borg.extract_archive(
            restore_request.repository,
            restore_request.archive,
            restore_request.paths,
            restore_request.destination,
            dry_run=False
        )
        return {"message": "Restore completed successfully"}
    except Exception as e:
        logger.error("Failed to start restore", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start restore"
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
    """Get all archives for a repository"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        result = await borg.list_archives(
            repository.path,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )

        # Parse borg list output
        archives = []
        if result.get("stdout"):
            for line in result["stdout"].strip().split("\n"):
                if line:
                    try:
                        archive_data = json.loads(line)
                        archives.append({
                            "id": archive_data.get("archive", {}).get("id"),
                            "name": archive_data.get("archive", {}).get("name"),
                            "timestamp": archive_data.get("archive", {}).get("start"),
                        })
                    except json.JSONDecodeError:
                        continue

        return {"archives": archives}
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