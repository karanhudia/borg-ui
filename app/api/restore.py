from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import structlog
from typing import List

from app.database.models import User
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