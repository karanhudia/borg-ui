"""
API endpoints for managing Borg archive mounts

Allows users to mount Borg repositories/archives for direct filesystem browsing
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import structlog

from app.database.database import get_db
from app.database.models import User
from app.core.security import get_current_user
from app.services.mount_service import mount_service, MountType
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(prefix="/api/mounts", tags=["mounts"])


# Request/Response models
class MountBorgRequest(BaseModel):
    """Request to mount a Borg repository or archive"""
    repository_id: int
    archive_name: Optional[str] = None
    mount_point: Optional[str] = None


class MountResponse(BaseModel):
    """Response after mounting"""
    mount_id: str
    mount_point: str
    mount_type: str
    source: str


class UnmountRequest(BaseModel):
    """Request to unmount"""
    force: bool = False


class MountListItem(BaseModel):
    """Mount list item"""
    mount_id: str
    mount_point: str
    mount_type: str
    source: str
    created_at: str
    job_id: Optional[int] = None


def serialize_mount(mount_info) -> Dict[str, Any]:
    """Serialize MountInfo to dict"""
    return {
        "mount_id": mount_info.mount_id,
        "mount_point": mount_info.mount_point,
        "mount_type": mount_info.mount_type.value,
        "source": mount_info.source,
        "created_at": serialize_datetime(mount_info.created_at),
        "job_id": mount_info.job_id,
        "repository_id": mount_info.repository_id,
        "connection_id": mount_info.connection_id
    }


@router.post("/borg", response_model=MountResponse)
async def mount_borg_archive(
    request: MountBorgRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mount a Borg repository or specific archive for browsing

    Args:
        repository_id: Repository ID to mount
        archive_name: Optional specific archive name (None = mount entire repo)
        mount_point: Optional custom mount point (will be validated for security)

    Returns:
        Mount information including mount_id and mount_point

    Note:
        - Mounted archives appear as read-only filesystems
        - Use the unmount endpoint to cleanup when done
        - Mount points are automatically cleaned up on container restart
    """
    try:
        logger.info(
            "User requesting Borg mount",
            user_id=current_user.id,
            username=current_user.username,
            repository_id=request.repository_id,
            archive_name=request.archive_name,
            mount_point=request.mount_point
        )

        # Mount the archive
        mount_point, mount_id = await mount_service.mount_borg_archive(
            repository_id=request.repository_id,
            archive_name=request.archive_name,
            mount_point=request.mount_point
        )

        # Get mount info
        mount_info = mount_service.get_mount(mount_id)
        if not mount_info:
            raise HTTPException(
                status_code=500,
                detail="Mount succeeded but info not found"
            )

        logger.info(
            "Successfully mounted Borg archive for user",
            user_id=current_user.id,
            mount_id=mount_id,
            mount_point=mount_point
        )

        return MountResponse(
            mount_id=mount_id,
            mount_point=mount_point,
            mount_type=mount_info.mount_type.value,
            source=mount_info.source
        )

    except Exception as e:
        logger.error(
            "Failed to mount Borg archive",
            user_id=current_user.id,
            repository_id=request.repository_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mount archive: {str(e)}"
        )


@router.post("/borg/unmount/{mount_id}")
async def unmount_borg_archive(
    mount_id: str,
    force: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Unmount a Borg archive

    Args:
        mount_id: Mount ID to unmount
        force: Force unmount even if busy (lazy unmount)

    Returns:
        Success status
    """
    try:
        logger.info(
            "User requesting unmount",
            user_id=current_user.id,
            username=current_user.username,
            mount_id=mount_id,
            force=force
        )

        # Verify mount exists
        mount_info = mount_service.get_mount(mount_id)
        if not mount_info:
            raise HTTPException(
                status_code=404,
                detail=f"Mount {mount_id} not found"
            )

        # Only allow unmounting Borg mounts (not backup job SSHFS mounts)
        if mount_info.mount_type != MountType.BORG_ARCHIVE:
            raise HTTPException(
                status_code=400,
                detail="Can only unmount Borg archive mounts via this endpoint"
            )

        # Unmount
        success = await mount_service.unmount(mount_id, force=force)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to unmount {mount_id}"
            )

        logger.info(
            "Successfully unmounted for user",
            user_id=current_user.id,
            mount_id=mount_id
        )

        return {"success": True, "mount_id": mount_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to unmount",
            user_id=current_user.id,
            mount_id=mount_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unmount: {str(e)}"
        )


@router.get("", response_model=List[MountListItem])
async def list_mounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all active mounts

    Returns list of active mounts visible to the user
    (currently shows all mounts, can be filtered by user in future)
    """
    try:
        logger.info(
            "User listing mounts",
            user_id=current_user.id,
            username=current_user.username
        )

        from app.database.models import Repository

        mounts = mount_service.list_mounts()

        # Filter to only user-facing mounts (Borg archives, not backup job SSHFS mounts)
        user_mounts = [
            m for m in mounts
            if m.mount_type == MountType.BORG_ARCHIVE
        ]

        # Fetch repository names
        repo_ids = [m.repository_id for m in user_mounts if m.repository_id]
        repositories = {}
        if repo_ids:
            repos = db.query(Repository).filter(Repository.id.in_(repo_ids)).all()
            repositories = {r.id: r.name for r in repos}

        # Update source with repository name
        result = []
        for m in user_mounts:
            source = m.source
            if m.repository_id and m.repository_id in repositories:
                # Replace path with repo name in source
                parts = source.split('::')
                if len(parts) > 1:
                    source = f"{repositories[m.repository_id]}::{parts[1]}"

            result.append(
                MountListItem(
                    mount_id=m.mount_id,
                    mount_point=m.mount_point,
                    mount_type=m.mount_type.value,
                    source=source,
                    created_at=serialize_datetime(m.created_at),
                    job_id=m.job_id
                )
            )

        return result

    except Exception as e:
        logger.error(
            "Failed to list mounts",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list mounts: {str(e)}"
        )


@router.get("/{mount_id}")
async def get_mount_info(
    mount_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get information about a specific mount

    Args:
        mount_id: Mount ID to query

    Returns:
        Mount information
    """
    try:
        mount_info = mount_service.get_mount(mount_id)

        if not mount_info:
            raise HTTPException(
                status_code=404,
                detail=f"Mount {mount_id} not found"
            )

        # Only show user-facing mounts
        if mount_info.mount_type != MountType.BORG_ARCHIVE:
            raise HTTPException(
                status_code=404,
                detail=f"Mount {mount_id} not found"
            )

        return serialize_mount(mount_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get mount info",
            user_id=current_user.id,
            mount_id=mount_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get mount info: {str(e)}"
        )
