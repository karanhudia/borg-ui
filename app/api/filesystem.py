"""
Filesystem browsing API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
import os
import subprocess
import structlog
from datetime import datetime

from app.core.security import get_current_user
from app.database.database import get_db
from sqlalchemy.orm import Session
from app.database.models import SSHKey

logger = structlog.get_logger()

router = APIRouter()


class FileSystemItem(BaseModel):
    """Represents a file or directory in the filesystem"""
    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None
    modified: Optional[str] = None
    is_borg_repo: bool = False
    permissions: Optional[str] = None


class BrowseResponse(BaseModel):
    """Response for filesystem browse operation"""
    current_path: str
    items: List[FileSystemItem]
    parent_path: Optional[str] = None


def is_borg_repository(path: str) -> bool:
    """
    Detect if a directory is a Borg repository by checking for required files/directories.

    A Borg repository must have:
    - config file (contains repository metadata)
    - data/ directory (stores deduplicated chunks)

    Optional indicators:
    - README file
    - lock.roster file
    - hints.* files
    """
    try:
        if not os.path.isdir(path):
            return False

        # Check for required Borg repository structure
        config_file = os.path.join(path, "config")
        data_dir = os.path.join(path, "data")

        has_config = os.path.isfile(config_file)
        has_data_dir = os.path.isdir(data_dir)

        # Both must exist for it to be a Borg repo
        if has_config and has_data_dir:
            # Additional validation: check if config file has Borg-specific content
            try:
                with open(config_file, 'r') as f:
                    content = f.read(100)  # Read first 100 bytes
                    # Borg config files typically start with [repository]
                    if '[repository]' in content:
                        return True
            except:
                pass

            # Even without reading config, if both exist, it's likely a Borg repo
            return True

        return False
    except Exception as e:
        logger.warning("Error checking if directory is Borg repo", path=path, error=str(e))
        return False


def is_borg_repository_ssh(host: str, username: str, ssh_key_path: str, remote_path: str, port: int = 22) -> bool:
    """
    Detect if a remote directory is a Borg repository via SSH.
    """
    try:
        # Check for config file and data directory
        check_cmd = f'[ -f "{remote_path}/config" ] && [ -d "{remote_path}/data" ] && echo "true" || echo "false"'

        ssh_cmd = [
            "ssh",
            "-i", ssh_key_path,
            "-p", str(port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=5",
            f"{username}@{host}",
            check_cmd
        ]

        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        return result.stdout.strip() == "true"
    except Exception as e:
        logger.warning("Error checking remote Borg repo", host=host, path=remote_path, error=str(e))
        return False


@router.get("/browse", response_model=BrowseResponse)
async def browse_filesystem(
    path: str = Query("/local", description="Path to browse"),
    connection_type: str = Query("local", description="Connection type: local or ssh"),
    ssh_key_id: Optional[int] = Query(None, description="SSH key ID for remote browsing"),
    host: Optional[str] = Query(None, description="SSH host"),
    username: Optional[str] = Query(None, description="SSH username"),
    port: int = Query(22, description="SSH port"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Browse filesystem directories.

    For local paths: browses the container's filesystem (including /local mount)
    For SSH paths: browses remote filesystem via SSH connection
    """
    try:
        if connection_type == "local":
            return await browse_local_filesystem(path)
        elif connection_type == "ssh":
            if not all([ssh_key_id, host, username]):
                raise HTTPException(
                    status_code=400,
                    detail="SSH key ID, host, and username are required for SSH browsing"
                )
            return await browse_ssh_filesystem(path, ssh_key_id, host, username, port, db)
        else:
            raise HTTPException(status_code=400, detail="Invalid connection type")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error browsing filesystem", path=path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to browse filesystem: {str(e)}")


async def browse_local_filesystem(path: str) -> BrowseResponse:
    """Browse local filesystem"""
    # Security: Prevent directory traversal attacks
    path = os.path.abspath(path)

    # Check if path exists
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    # Check if path is a directory
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

    items = []

    try:
        # List directory contents
        entries = os.listdir(path)
        entries.sort(key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))

        for entry in entries:
            try:
                full_path = os.path.join(path, entry)
                stat_info = os.stat(full_path)
                is_dir = os.path.isdir(full_path)

                # Check if directory is a Borg repository
                is_borg = False
                if is_dir:
                    is_borg = is_borg_repository(full_path)

                item = FileSystemItem(
                    name=entry,
                    path=full_path,
                    is_directory=is_dir,
                    size=stat_info.st_size if not is_dir else None,
                    modified=datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                    is_borg_repo=is_borg,
                    permissions=oct(stat_info.st_mode)[-3:]
                )
                items.append(item)
            except (PermissionError, OSError) as e:
                # Skip items we can't access
                logger.debug("Skipping inaccessible item", item=entry, error=str(e))
                continue

        # Get parent path
        parent_path = os.path.dirname(path) if path != "/" else None

        return BrowseResponse(
            current_path=path,
            items=items,
            parent_path=parent_path
        )

    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")


async def browse_ssh_filesystem(
    path: str,
    ssh_key_id: int,
    host: str,
    username: str,
    port: int,
    db: Session
) -> BrowseResponse:
    """Browse remote filesystem via SSH"""
    # Get SSH key
    ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
    if not ssh_key:
        raise HTTPException(status_code=404, detail="SSH key not found")

    ssh_key_path = ssh_key.private_key_path

    # Verify SSH key file exists
    if not os.path.exists(ssh_key_path):
        raise HTTPException(status_code=500, detail="SSH key file not found on server")

    try:
        # Use SSH to list directory contents
        # Format: ls -la --time-style=+%s output with parsing
        ls_cmd = f'ls -lA --time-style=+%s "{path}" 2>/dev/null || echo "ERROR"'

        ssh_cmd = [
            "ssh",
            "-i", ssh_key_path,
            "-p", str(port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            f"{username}@{host}",
            ls_cmd
        ]

        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0 or "ERROR" in result.stdout:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list remote directory: {result.stderr or 'Permission denied or path not found'}"
            )

        # Parse ls output
        items = []
        lines = result.stdout.strip().split('\n')

        for line in lines:
            if not line or line.startswith('total'):
                continue

            try:
                # Parse ls -la output
                # Format: drwxr-xr-x 2 user group 4096 1234567890 name
                parts = line.split(None, 8)
                if len(parts) < 9:
                    continue

                permissions = parts[0]
                size = int(parts[4])
                timestamp = int(parts[5])
                name = parts[8]

                # Skip . and ..
                if name in ['.', '..']:
                    continue

                is_dir = permissions.startswith('d')
                full_path = os.path.join(path, name)

                # Check if directory is a Borg repository
                is_borg = False
                if is_dir:
                    is_borg = is_borg_repository_ssh(host, username, ssh_key_path, full_path, port)

                item = FileSystemItem(
                    name=name,
                    path=full_path,
                    is_directory=is_dir,
                    size=size if not is_dir else None,
                    modified=datetime.fromtimestamp(timestamp).isoformat(),
                    is_borg_repo=is_borg,
                    permissions=permissions[1:] if len(permissions) > 1 else None
                )
                items.append(item)
            except (ValueError, IndexError) as e:
                logger.debug("Failed to parse ls line", line=line, error=str(e))
                continue

        # Sort: directories first, then by name
        items.sort(key=lambda x: (not x.is_directory, x.name.lower()))

        # Get parent path
        parent_path = os.path.dirname(path) if path != "/" else None

        return BrowseResponse(
            current_path=path,
            items=items,
            parent_path=parent_path
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="SSH connection timeout")
    except Exception as e:
        logger.error("Error browsing SSH filesystem", host=host, path=path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to browse remote filesystem: {str(e)}")


@router.post("/validate-path")
async def validate_path(
    path: str = Query(..., description="Path to validate"),
    connection_type: str = Query("local", description="Connection type"),
    ssh_key_id: Optional[int] = Query(None),
    host: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    port: int = Query(22),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Validate if a path exists and is accessible.
    Returns info about the path including if it's a Borg repository.
    """
    try:
        if connection_type == "local":
            exists = os.path.exists(path)
            is_dir = os.path.isdir(path) if exists else False
            is_borg = is_borg_repository(path) if is_dir else False

            return {
                "exists": exists,
                "is_directory": is_dir,
                "is_borg_repo": is_borg,
                "path": path
            }
        elif connection_type == "ssh":
            if not all([ssh_key_id, host, username]):
                raise HTTPException(status_code=400, detail="SSH parameters required")

            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
            if not ssh_key:
                raise HTTPException(status_code=404, detail="SSH key not found")

            # Check if path exists via SSH
            check_cmd = f'[ -e "{path}" ] && echo "exists" || echo "not_exists"; [ -d "{path}" ] && echo "is_dir" || echo "not_dir"'

            ssh_cmd = [
                "ssh",
                "-i", ssh_key.private_key_path,
                "-p", str(port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=5",
                f"{username}@{host}",
                check_cmd
            ]

            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)
            lines = result.stdout.strip().split('\n')

            exists = lines[0] == "exists" if len(lines) > 0 else False
            is_dir = lines[1] == "is_dir" if len(lines) > 1 else False
            is_borg = is_borg_repository_ssh(host, username, ssh_key.private_key_path, path, port) if is_dir else False

            return {
                "exists": exists,
                "is_directory": is_dir,
                "is_borg_repo": is_borg,
                "path": path
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid connection type")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error validating path", path=path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to validate path: {str(e)}")
