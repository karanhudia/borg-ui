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
from app.database.models import User, Repository
from app.core.authorization import authorize_request
from app.core.security import get_current_user, check_repo_access
from app.services.mount_service import mount_service, MountType, MountUnavailableError
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(
    prefix="/api/mounts", tags=["mounts"], dependencies=[Depends(authorize_request)]
)


def _require_mount_repo_access(
    db: Session, user: User, repository_id: Optional[int], role: str
) -> Optional[Repository]:
    """Gate a mount operation on the repository it targets.

    A mount exposes an archive's real file contents through the mount point, so
    it needs the same repo-scoped authorization as the archive endpoints. A
    mount whose repository is missing (no id, or the row was deleted while the
    mount is still active) stays reachable to an admin so orphaned mounts can be
    cleaned up, and is denied to everyone else.

    Returns the repository it resolved, so a caller that needs the row asks
    the database once.
    """
    if repository_id is None:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail={"key": "backend.errors.auth.notEnoughPermissions"},
            )
        return None
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        if user.role == "admin":
            return None
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.restore.repositoryNotFound"}
        )
    check_repo_access(db, user, repository, role)
    return repository


# Request/Response models
class MountBorgRequest(BaseModel):
    """Request to mount a Borg repository or archive"""

    repository_id: int
    archive_name: Optional[str] = None
    mount_point: Optional[str] = None
    # Borg 2 series archives share one name; the id addresses exactly one.
    archive_id: Optional[str] = None


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
        "connection_id": mount_info.connection_id,
    }


@router.post("/borg", response_model=MountResponse)
async def mount_borg_archive(
    request: MountBorgRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    # Mounting exposes the archive's real file contents, so require operator on
    # the target repository (not just the global mount policy). Kept outside the
    # try/except below so the 403 is not swallowed into a 500.
    repository = _require_mount_repo_access(
        db, current_user, request.repository_id, "operator"
    )

    # The mount service mounts under this server's data directory. An
    # agent-executed repository lives on the agent, so the server has neither
    # the repository nor the agent's filesystem to mount it on.
    if repository is not None and (repository.executor_type or "server") == "agent":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.mounts.agentRepository"},
        )

    try:
        logger.info(
            "User requesting Borg mount",
            user_id=current_user.id,
            username=current_user.username,
            repository_id=request.repository_id,
            archive_name=request.archive_name,
            mount_point=request.mount_point,
        )

        # Mount the archive
        mount_point, mount_id = await mount_service.mount_borg_archive(
            repository_id=request.repository_id,
            archive_name=request.archive_name,
            mount_point=request.mount_point,
            archive_id=request.archive_id,
        )

        # Get mount info
        mount_info = mount_service.get_mount(mount_id)
        if not mount_info:
            raise HTTPException(
                status_code=500,
                detail={"key": "backend.errors.mounts.mountInfoNotFound"},
            )

        logger.info(
            "Successfully mounted Borg archive for user",
            user_id=current_user.id,
            mount_id=mount_id,
            mount_point=mount_point,
        )

        return MountResponse(
            mount_id=mount_id,
            mount_point=mount_point,
            mount_type=mount_info.mount_type.value,
            source=mount_info.source,
        )

    except MountUnavailableError as e:
        logger.error(
            "Archive mounting unavailable",
            user_id=current_user.id,
            repository_id=request.repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=503, detail={"key": e.error_key, "params": {"error": str(e)}}
        )
    except Exception as e:
        logger.error(
            "Failed to mount Borg archive",
            user_id=current_user.id,
            repository_id=request.repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.mounts.failedMountArchive",
                "params": {"error": str(e)},
            },
        )


@router.post("/borg/unmount/{mount_id}")
async def unmount_borg_archive(
    mount_id: str,
    force: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
            force=force,
        )

        # Verify mount exists
        mount_info = mount_service.get_mount(mount_id)
        if not mount_info:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.mounts.mountNotFound",
                    "params": {"mountId": mount_id},
                },
            )

        # Unmounting another user's mount needs operator on its repository.
        _require_mount_repo_access(
            db, current_user, mount_info.repository_id, "operator"
        )

        # Only allow unmounting Borg mounts (not backup job SSHFS mounts)
        if mount_info.mount_type != MountType.BORG_ARCHIVE:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.mounts.canOnlyUnmountBorgMounts"},
            )

        # Unmount
        success = await mount_service.unmount(mount_id, force=force)

        if not success:
            raise HTTPException(
                status_code=500,
                detail={
                    "key": "backend.errors.mounts.unmountFailed",
                    "params": {"mountId": mount_id},
                },
            )

        logger.info(
            "Successfully unmounted for user",
            user_id=current_user.id,
            mount_id=mount_id,
        )

        return {"success": True, "mount_id": mount_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to unmount",
            user_id=current_user.id,
            mount_id=mount_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.mounts.failedUnmount",
                "params": {"error": str(e)},
            },
        )


@router.get("", response_model=List[MountListItem])
def list_mounts(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
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
            username=current_user.username,
        )

        mounts = mount_service.list_mounts()

        # Filter to only user-facing mounts (Borg archives, not backup job SSHFS mounts)
        borg_mounts = [m for m in mounts if m.mount_type == MountType.BORG_ARCHIVE]

        # Only expose mounts on repositories the user may view. Mounts are
        # global (shared across users), so without this filter any user sees
        # every mount's repo, archive, mount point and job id.
        def _may_view(m) -> bool:
            try:
                _require_mount_repo_access(db, current_user, m.repository_id, "viewer")
                return True
            except HTTPException:
                return False

        user_mounts = [m for m in borg_mounts if _may_view(m)]

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
                parts = source.split("::")
                if len(parts) > 1:
                    source = f"{repositories[m.repository_id]}::{parts[1]}"

            result.append(
                MountListItem(
                    mount_id=m.mount_id,
                    mount_point=m.mount_point,
                    mount_type=m.mount_type.value,
                    source=source,
                    created_at=serialize_datetime(m.created_at),
                    job_id=m.job_id,
                )
            )

        return result

    except Exception as e:
        logger.error("Failed to list mounts", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.mounts.failedListMounts",
                "params": {"error": str(e)},
            },
        )


@router.get("/{mount_id}")
def get_mount_info(
    mount_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
                detail={
                    "key": "backend.errors.mounts.mountNotFound",
                    "params": {"mountId": mount_id},
                },
            )

        # Only show user-facing mounts
        if mount_info.mount_type != MountType.BORG_ARCHIVE:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.mounts.mountNotFound",
                    "params": {"mountId": mount_id},
                },
            )

        _require_mount_repo_access(db, current_user, mount_info.repository_id, "viewer")

        return serialize_mount(mount_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get mount info",
            user_id=current_user.id,
            mount_id=mount_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.mounts.failedGetMountInfo",
                "params": {"error": str(e)},
            },
        )
