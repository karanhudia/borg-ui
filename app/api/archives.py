from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog
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
    """Get information about a specific archive"""
    try:
        result = await borg.info_archive(repository, archive_id)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive info: {result['stderr']}"
            )
        
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