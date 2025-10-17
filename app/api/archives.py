from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog
import json
from typing import List, Dict, Any

from app.database.database import get_db
from app.database.models import User
from app.core.security import get_current_user
from app.core.borg import borg

logger = structlog.get_logger()
router = APIRouter()

@router.get("/list")
async def list_archives(
    repository: str,
    current_user: User = Depends(get_current_user)
):
    """List archives in a repository"""
    try:
        result = await borg.list_archives(repository)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list archives: {result['stderr']}"
            )
        
        return {"archives": result["stdout"]}
    except Exception as e:
        logger.error("Failed to list archives", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list archives"
        )

@router.get("/{archive_id}/info")
async def get_archive_info(
    repository: str,
    archive_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get detailed information about a specific archive including command line and metadata"""
    try:
        result = await borg.info_archive(repository, archive_id)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive info: {result['stderr']}"
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

            return {"info": enhanced_info}

        except json.JSONDecodeError:
            # Fallback to raw output if not JSON
            logger.warning("Archive info is not JSON, returning raw output")
            return {"info": result["stdout"]}

    except Exception as e:
        logger.error("Failed to get archive info", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get archive info"
        )

@router.get("/{archive_id}/contents")
async def get_archive_contents(
    repository: str,
    archive_id: str,
    path: str = "",
    current_user: User = Depends(get_current_user)
):
    """Get contents of an archive"""
    try:
        result = await borg.list_archive_contents(repository, archive_id, path)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive contents: {result['stderr']}"
            )
        
        return {"contents": result["stdout"]}
    except Exception as e:
        logger.error("Failed to get archive contents", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get archive contents"
        )

@router.delete("/{archive_id}")
async def delete_archive(
    repository: str,
    archive_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete an archive"""
    try:
        result = await borg.delete_archive(repository, archive_id)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete archive: {result['stderr']}"
            )
        
        return {"message": "Archive deleted successfully"}
    except Exception as e:
        logger.error("Failed to delete archive", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete archive"
        ) 