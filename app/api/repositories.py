from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import structlog
import os
import subprocess
import asyncio
import json

from app.database.database import get_db
from app.database.models import User, Repository
from app.core.security import get_current_user
from app.core.borg import BorgInterface
from app.core.repository_locks import with_repository_lock
from app.config import settings

logger = structlog.get_logger()
router = APIRouter(tags=["repositories"])

# Initialize Borg interface
borg = BorgInterface()

# Helper function to setup Borg environment with proper lock configuration
def setup_borg_env(base_env=None, passphrase=None, ssh_opts=None):
    """Setup Borg environment variables with lock and timeout configuration"""
    env = base_env.copy() if base_env else os.environ.copy()

    # Set passphrase if provided
    if passphrase:
        env["BORG_PASSPHRASE"] = passphrase

    # Allow non-interactive access to unencrypted repositories
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"

    # Configure lock behavior to prevent timeout issues
    # Wait up to 180 seconds (3 minutes) for locks instead of default 1 second
    env["BORG_LOCK_WAIT"] = "180"

    # Mark this container's hostname as unique to avoid lock conflicts
    # This prevents issues when multiple operations run on same repository
    env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

    # Set SSH options if provided
    if ssh_opts:
        env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

    return env

# Helper function to format datetime with timezone
def format_datetime(dt):
    """Format datetime to ISO8601 with UTC timezone indicator"""
    if dt is None:
        return None
    # If datetime is naive (no timezone), assume it's UTC and add timezone info
    if dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

# Pydantic models
from pydantic import BaseModel

class RepositoryCreate(BaseModel):
    name: str
    path: str
    encryption: str = "repokey"  # repokey, keyfile, none
    compression: str = "lz4"  # lz4, zstd, zlib, none
    passphrase: Optional[str] = None
    source_directories: Optional[List[str]] = None  # List of directories to backup
    exclude_patterns: Optional[List[str]] = None  # List of exclude patterns (e.g., ["*.log", "*.tmp"])
    repository_type: str = "local"  # local, ssh, sftp
    host: Optional[str] = None  # For SSH repositories
    port: Optional[int] = 22  # SSH port
    username: Optional[str] = None  # SSH username
    ssh_key_id: Optional[int] = None  # Associated SSH key ID
    remote_path: Optional[str] = None  # Path to borg on remote server (e.g., /usr/local/bin/borg)
    pre_backup_script: Optional[str] = None  # Script to run before backup
    post_backup_script: Optional[str] = None  # Script to run after backup
    hook_timeout: Optional[int] = 300  # Hook timeout in seconds
    continue_on_hook_failure: Optional[bool] = False  # Continue backup if pre-hook fails

class RepositoryImport(BaseModel):
    name: str
    path: str
    passphrase: Optional[str] = None  # Required if repository is encrypted
    compression: str = "lz4"  # Default compression for future backups
    source_directories: Optional[List[str]] = None  # List of directories to backup
    exclude_patterns: Optional[List[str]] = None  # List of exclude patterns
    repository_type: str = "local"  # local, ssh, sftp
    host: Optional[str] = None  # For SSH repositories
    port: Optional[int] = 22  # SSH port
    username: Optional[str] = None  # SSH username
    ssh_key_id: Optional[int] = None  # Associated SSH key ID
    remote_path: Optional[str] = None  # Path to borg on remote server
    pre_backup_script: Optional[str] = None  # Script to run before backup
    post_backup_script: Optional[str] = None  # Script to run after backup
    hook_timeout: Optional[int] = 300  # Hook timeout in seconds
    continue_on_hook_failure: Optional[bool] = False  # Continue backup if pre-hook fails

class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    compression: Optional[str] = None
    source_directories: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    remote_path: Optional[str] = None
    pre_backup_script: Optional[str] = None
    post_backup_script: Optional[str] = None
    hook_timeout: Optional[int] = None
    continue_on_hook_failure: Optional[bool] = None

class RepositoryInfo(BaseModel):
    id: int
    name: str
    path: str
    encryption: str
    compression: str
    source_directories: Optional[List[str]]
    last_backup: Optional[str]
    total_size: Optional[str]
    archive_count: int
    is_active: bool
    created_at: str
    updated_at: Optional[str]

@router.get("/")
async def get_repositories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all repositories"""
    try:
        repositories = db.query(Repository).all()
        return {
            "success": True,
            "repositories": [
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "encryption": repo.encryption,
                    "compression": repo.compression,
                    "source_directories": json.loads(repo.source_directories) if repo.source_directories else [],
                    "exclude_patterns": json.loads(repo.exclude_patterns) if repo.exclude_patterns else [],
                    "last_backup": format_datetime(repo.last_backup),
                    "total_size": repo.total_size,
                    "archive_count": repo.archive_count,
                    "created_at": format_datetime(repo.created_at),
                    "updated_at": format_datetime(repo.updated_at),
                    "pre_backup_script": repo.pre_backup_script,
                    "post_backup_script": repo.post_backup_script,
                    "hook_timeout": repo.hook_timeout,
                    "continue_on_hook_failure": repo.continue_on_hook_failure
                }
                for repo in repositories
            ]
        }
    except Exception as e:
        logger.error("Failed to get repositories", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve repositories: {str(e)}")

@router.post("/")
async def create_repository(
    repo_data: RepositoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new repository"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Validate source directories are provided
        if not repo_data.source_directories or len(repo_data.source_directories) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one source directory is required. Source directories specify what data will be backed up to this repository."
            )

        # Validate passphrase for encrypted repositories
        if repo_data.encryption in ["repokey", "keyfile", "repokey-blake2", "keyfile-blake2"]:
            if not repo_data.passphrase or repo_data.passphrase.strip() == "":
                raise HTTPException(
                    status_code=400,
                    detail=f"Passphrase is required for encryption mode '{repo_data.encryption}'. Use encryption='none' for unencrypted repositories."
                )

        # Validate repository type and path
        repo_path = repo_data.path.strip()

        if repo_data.repository_type == "local":
            # For local repositories, ensure path is absolute
            if not os.path.isabs(repo_path):
                # If relative path, make it relative to data directory
                repo_path = os.path.join(settings.data_dir, repo_path)

            # Validate that the path is a valid absolute path
            repo_path = os.path.abspath(repo_path)
        elif repo_data.repository_type in ["ssh", "sftp"]:
            # For SSH repositories, validate required fields
            if not repo_data.host:
                raise HTTPException(status_code=400, detail="Host is required for SSH repositories")
            if not repo_data.username:
                raise HTTPException(status_code=400, detail="Username is required for SSH repositories")
            if not repo_data.ssh_key_id:
                raise HTTPException(status_code=400, detail="SSH key is required for SSH repositories")

            # Check if borg is installed on remote machine
            logger.info("Checking if borg is installed on remote machine",
                       host=repo_data.host,
                       username=repo_data.username)

            remote_check = await check_remote_borg_installation(
                repo_data.host,
                repo_data.username,
                repo_data.port,
                repo_data.ssh_key_id
            )

            if not remote_check.get("has_borg"):
                install_cmd = "apt-get install borgbackup" if "debian" in remote_check.get("error", "").lower() else "yum install borgbackup"
                raise HTTPException(
                    status_code=400,
                    detail=f"Borg Backup is not installed on {repo_data.username}@{repo_data.host}. "
                           f"Please install it first:\n\n"
                           f"Ubuntu/Debian: sudo apt-get update && sudo apt-get install borgbackup\n"
                           f"Fedora/RHEL: sudo dnf install borgbackup\n"
                           f"Arch: sudo pacman -S borg\n\n"
                           f"Or visit: https://borgbackup.readthedocs.io/en/stable/installation.html"
                )

            logger.info("Remote borg check passed",
                       host=repo_data.host,
                       has_borg=remote_check.get("has_borg"),
                       borg_path=remote_check.get("borg_path"))

            # Build SSH repository path
            # If path already starts with ssh://, extract just the remote path
            if repo_path.startswith("ssh://"):
                # Parse the SSH URL to extract the path component
                import re
                match = re.match(r"ssh://[^/]+(/.*)", repo_path)
                if match:
                    repo_path = match.group(1)
                else:
                    # Fallback: strip ssh:// and extract path after host
                    repo_path = repo_path.split("/", 3)[-1] if "/" in repo_path else repo_path

            repo_path = f"ssh://{repo_data.username}@{repo_data.host}:{repo_data.port}/{repo_path.lstrip('/')}"
        else:
            raise HTTPException(status_code=400, detail="Invalid repository type. Must be 'local', 'ssh', or 'sftp'")
        
        # Check if repository name already exists
        existing_repo = db.query(Repository).filter(Repository.name == repo_data.name).first()
        if existing_repo:
            raise HTTPException(status_code=400, detail="Repository name already exists")
        
        # Check if repository path already exists
        existing_path = db.query(Repository).filter(Repository.path == repo_path).first()
        if existing_path:
            raise HTTPException(status_code=400, detail="Repository path already exists")
        
        # Create repository directory if local (but not if using /local mount)
        if repo_data.repository_type == "local":
            # Skip directory creation if path is within /local mount (host filesystem)
            # User must ensure parent directory exists with proper permissions
            if not repo_path.startswith("/local/"):
                # Paths without /local/ prefix are inside the container
                # Try to create the directory, but provide helpful error if permission denied
                try:
                    os.makedirs(repo_path, exist_ok=True)
                except PermissionError as e:
                    logger.error("Permission denied creating repository directory",
                               path=repo_path,
                               error=str(e))
                    raise HTTPException(
                        status_code=400,
                        detail=f"Permission denied: Cannot create directory at '{repo_path}'. "
                               f"To store repositories on your host machine, use paths starting with '/local/' "
                               f"(e.g., '/local{repo_path}' for accessing your host filesystem). "
                               f"The container's root filesystem (/) is mapped to /local/ inside the container."
                    )
            else:
                # For /local/ paths, we need to ensure the parent directory exists
                # Let's try to create the full path up to the repository directory
                parent_dir = os.path.dirname(repo_path)
                logger.info("Checking /local mount path",
                          repo_path=repo_path,
                          parent_dir=parent_dir,
                          parent_exists=os.path.exists(parent_dir))

                # Try to create parent directories if they don't exist
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                    logger.info("Created parent directories", parent_dir=parent_dir)
                except PermissionError as e:
                    logger.error("Permission denied creating parent directories",
                               parent_dir=parent_dir,
                               error=str(e))
                    raise HTTPException(
                        status_code=400,
                        detail=f"Permission denied: Cannot create parent directory '{parent_dir}'. "
                               f"Please ensure the directory exists on your host machine and has proper permissions. "
                               f"On your host: sudo mkdir -p {parent_dir.replace('/local', '')} && sudo chown -R $(whoami) {parent_dir.replace('/local', '')}"
                    )
                except Exception as e:
                    logger.error("Failed to create parent directories",
                               parent_dir=parent_dir,
                               error=str(e))
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to create parent directory: {str(e)}"
                    )

                # Verify parent directory is writable
                if not os.access(parent_dir, os.W_OK):
                    logger.error("Parent directory is not writable",
                               parent_dir=parent_dir)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Parent directory is not writable: {parent_dir}. "
                               f"On your host machine, run: sudo chown -R $(whoami) {parent_dir.replace('/local', '')}"
                    )
        
        # Initialize Borg repository
        init_result = await initialize_borg_repository(
            repo_path,
            repo_data.encryption,
            repo_data.passphrase,
            repo_data.ssh_key_id if repo_data.repository_type in ["ssh", "sftp"] else None
        )

        if not init_result["success"]:
            raise HTTPException(status_code=500, detail=f"Failed to initialize repository: {init_result['error']}")

        # Serialize source directories as JSON
        source_directories_json = None
        if repo_data.source_directories:
            source_directories_json = json.dumps(repo_data.source_directories)

        # Serialize exclude patterns as JSON
        exclude_patterns_json = None
        if repo_data.exclude_patterns:
            exclude_patterns_json = json.dumps(repo_data.exclude_patterns)

        # Create repository record
        repository = Repository(
            name=repo_data.name,
            path=repo_path,
            encryption=repo_data.encryption,
            compression=repo_data.compression,
            passphrase=repo_data.passphrase,  # Store passphrase for backups
            source_directories=source_directories_json,
            exclude_patterns=exclude_patterns_json,
            repository_type=repo_data.repository_type,
            host=repo_data.host,
            port=repo_data.port,
            username=repo_data.username,
            ssh_key_id=repo_data.ssh_key_id,
            remote_path=repo_data.remote_path,
            pre_backup_script=repo_data.pre_backup_script,
            post_backup_script=repo_data.post_backup_script,
            hook_timeout=repo_data.hook_timeout,
            continue_on_hook_failure=repo_data.continue_on_hook_failure
        )

        db.add(repository)
        db.commit()
        db.refresh(repository)

        # Determine response message
        already_existed = init_result.get("already_existed", False)
        if already_existed:
            message = "Repository already exists at this location and has been added to the UI"
            logger.info("Existing repository added", name=repo_data.name, path=repo_path, user=current_user.username)
        else:
            message = "Repository created successfully"
            logger.info("Repository created", name=repo_data.name, path=repo_path, user=current_user.username)

        return {
            "success": True,
            "message": message,
            "already_existed": already_existed,
            "repository": {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path,
                "encryption": repository.encryption,
                "compression": repository.compression
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create repository: {str(e)}")

@router.post("/import")
async def import_repository(
    repo_data: RepositoryImport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Import an existing Borg repository"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Validate source directories are provided
        if not repo_data.source_directories or len(repo_data.source_directories) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one source directory is required. Source directories specify what data will be backed up to this repository."
            )

        # Validate repository type and path
        repo_path = repo_data.path.strip()

        if repo_data.repository_type == "local":
            # For local repositories, ensure path is absolute
            if not os.path.isabs(repo_path):
                # If relative path, make it relative to data directory
                repo_path = os.path.join(settings.data_dir, repo_path)

            # Validate that the path is a valid absolute path
            repo_path = os.path.abspath(repo_path)

            # Check if repository directory exists
            if not os.path.exists(repo_path):
                raise HTTPException(
                    status_code=400,
                    detail=f"Repository directory does not exist: {repo_path}"
                )

            # Check if it's a valid Borg repository by looking for config file
            config_path = os.path.join(repo_path, "config")
            if not os.path.exists(config_path):
                raise HTTPException(
                    status_code=400,
                    detail=f"Not a valid Borg repository: {repo_path}. Missing 'config' file."
                )

        elif repo_data.repository_type in ["ssh", "sftp"]:
            # For SSH repositories, validate required fields
            if not repo_data.host:
                raise HTTPException(status_code=400, detail="Host is required for SSH repositories")
            if not repo_data.username:
                raise HTTPException(status_code=400, detail="Username is required for SSH repositories")
            if not repo_data.ssh_key_id:
                raise HTTPException(status_code=400, detail="SSH key is required for SSH repositories")

            # Check if borg is installed on remote machine
            logger.info("Checking if borg is installed on remote machine",
                       host=repo_data.host,
                       username=repo_data.username)

            remote_check = await check_remote_borg_installation(
                repo_data.host,
                repo_data.username,
                repo_data.port,
                repo_data.ssh_key_id
            )

            if not remote_check.get("has_borg"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Borg Backup is not installed on {repo_data.username}@{repo_data.host}. "
                           f"Please install it first:\n\n"
                           f"Ubuntu/Debian: sudo apt-get update && sudo apt-get install borgbackup\n"
                           f"Fedora/RHEL: sudo dnf install borgbackup\n"
                           f"Arch: sudo pacman -S borg\n\n"
                           f"Or visit: https://borgbackup.readthedocs.io/en/stable/installation.html"
                )

            # Build SSH repository path
            if repo_path.startswith("ssh://"):
                # Parse the SSH URL to extract the path component
                import re
                match = re.match(r"ssh://[^/]+(/.*)", repo_path)
                if match:
                    repo_path = match.group(1)
                else:
                    repo_path = repo_path.split("/", 3)[-1] if "/" in repo_path else repo_path

            repo_path = f"ssh://{repo_data.username}@{repo_data.host}:{repo_data.port}/{repo_path.lstrip('/')}"
        else:
            raise HTTPException(status_code=400, detail="Invalid repository type. Must be 'local', 'ssh', or 'sftp'")

        # Check if repository name already exists
        existing_repo = db.query(Repository).filter(Repository.name == repo_data.name).first()
        if existing_repo:
            raise HTTPException(status_code=400, detail="Repository name already exists in the database")

        # Check if repository path already exists in database
        existing_path = db.query(Repository).filter(Repository.path == repo_path).first()
        if existing_path:
            raise HTTPException(
                status_code=400,
                detail=f"Repository path already exists in database with name '{existing_path.name}'"
            )

        # Verify repository is accessible by running borg info
        logger.info("Verifying repository accessibility", path=repo_path)
        verify_result = await verify_existing_repository(
            repo_path,
            repo_data.passphrase,
            repo_data.ssh_key_id if repo_data.repository_type in ["ssh", "sftp"] else None,
            repo_data.remote_path
        )

        if not verify_result["success"]:
            error_msg = verify_result.get("error", "Unknown error")

            # Provide helpful error messages
            if "passphrase" in error_msg.lower() or "encrypted" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="Repository is encrypted but passphrase is incorrect or missing. "
                           "Please provide the correct passphrase."
                )
            elif "not a valid repository" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail=f"Not a valid Borg repository: {repo_path}"
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to verify repository: {error_msg}"
                )

        # Extract repository info from verification
        repo_info = verify_result.get("info", {})
        encryption_mode = repo_info.get("encryption", {}).get("mode", "unknown")

        # Serialize source directories as JSON
        source_directories_json = None
        if repo_data.source_directories:
            source_directories_json = json.dumps(repo_data.source_directories)

        # Serialize exclude patterns as JSON
        exclude_patterns_json = None
        if repo_data.exclude_patterns:
            exclude_patterns_json = json.dumps(repo_data.exclude_patterns)

        # Create repository record
        repository = Repository(
            name=repo_data.name,
            path=repo_path,
            encryption=encryption_mode,
            compression=repo_data.compression,
            passphrase=repo_data.passphrase,
            source_directories=source_directories_json,
            exclude_patterns=exclude_patterns_json,
            repository_type=repo_data.repository_type,
            host=repo_data.host,
            port=repo_data.port,
            username=repo_data.username,
            ssh_key_id=repo_data.ssh_key_id,
            remote_path=repo_data.remote_path,
            archive_count=len(repo_info.get("archives", [])) if "archives" in repo_info else 0,
            pre_backup_script=repo_data.pre_backup_script,
            post_backup_script=repo_data.post_backup_script,
            hook_timeout=repo_data.hook_timeout,
            continue_on_hook_failure=repo_data.continue_on_hook_failure
        )

        db.add(repository)
        db.commit()
        db.refresh(repository)

        logger.info("Repository imported successfully",
                   name=repo_data.name,
                   path=repo_path,
                   user=current_user.username,
                   archive_count=repository.archive_count)

        return {
            "success": True,
            "message": "Repository imported successfully",
            "repository": {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path,
                "encryption": repository.encryption,
                "compression": repository.compression,
                "archive_count": repository.archive_count
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to import repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to import repository: {str(e)}")

@router.get("/{repo_id}")
async def get_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get repository details"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Get repository statistics
        stats = await get_repository_stats(repository.path)
        
        return {
            "success": True,
            "repository": {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path,
                "encryption": repository.encryption,
                "compression": repository.compression,
                "last_backup": format_datetime(repository.last_backup),
                "total_size": repository.total_size,
                "archive_count": repository.archive_count,
                "created_at": format_datetime(repository.created_at),
                "updated_at": format_datetime(repository.updated_at),
                "stats": stats
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve repository: {str(e)}")

@router.put("/{repo_id}")
async def update_repository(
    repo_id: int,
    repo_data: RepositoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update repository"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Update fields
        if repo_data.name is not None:
            # Check if name already exists
            existing_repo = db.query(Repository).filter(
                Repository.name == repo_data.name,
                Repository.id != repo_id
            ).first()
            if existing_repo:
                raise HTTPException(status_code=400, detail="Repository name already exists")
            repository.name = repo_data.name
        
        if repo_data.path is not None:
            # Check if path already exists
            existing_path = db.query(Repository).filter(
                Repository.path == repo_data.path,
                Repository.id != repo_id
            ).first()
            if existing_path:
                raise HTTPException(status_code=400, detail="Repository path already exists")
            repository.path = repo_data.path
        
        if repo_data.compression is not None:
            repository.compression = repo_data.compression

        if repo_data.source_directories is not None:
            repository.source_directories = json.dumps(repo_data.source_directories)

        if repo_data.exclude_patterns is not None:
            repository.exclude_patterns = json.dumps(repo_data.exclude_patterns)

        if repo_data.remote_path is not None:
            repository.remote_path = repo_data.remote_path

        if repo_data.pre_backup_script is not None:
            repository.pre_backup_script = repo_data.pre_backup_script

        if repo_data.post_backup_script is not None:
            repository.post_backup_script = repo_data.post_backup_script

        if repo_data.hook_timeout is not None:
            repository.hook_timeout = repo_data.hook_timeout

        if repo_data.continue_on_hook_failure is not None:
            repository.continue_on_hook_failure = repo_data.continue_on_hook_failure

        repository.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info("Repository updated", repo_id=repo_id, user=current_user.username)
        
        return {
            "success": True,
            "message": "Repository updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update repository: {str(e)}")

@router.delete("/{repo_id}")
async def delete_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete repository (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Check if repository has archives
        archives_result = await borg.list_archives(repository.path, remote_path=repository.remote_path)
        if archives_result["success"]:
            try:
                archives_data = archives_result["stdout"]
                if archives_data and len(archives_data) > 0:
                    raise HTTPException(
                        status_code=400, 
                        detail="Cannot delete repository with existing archives. Please delete all archives first."
                    )
            except:
                pass
        
        # Delete repository from database
        db.delete(repository)
        db.commit()
        
        logger.info("Repository deleted", repo_id=repo_id, user=current_user.username)
        
        return {
            "success": True,
            "message": "Repository deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete repository: {str(e)}")

@router.post("/{repo_id}/check")
async def check_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check repository integrity"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Run repository check
        check_result = await borg.check_repository(
            repository.path,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )
        
        return {
            "success": True,
            "check_result": check_result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to check repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to check repository: {str(e)}")

@router.post("/{repo_id}/compact")
async def compact_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compact repository to free space"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Run repository compaction
        compact_result = await borg.compact_repository(
            repository.path,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )

        return {
            "success": True,
            "compact_result": compact_result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to compact repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to compact repository: {str(e)}")

@router.post("/{repo_id}/prune")
async def prune_repository(
    repo_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Prune old archives based on retention policy"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Extract retention policy from request
        keep_daily = request.get("keep_daily", 7)
        keep_weekly = request.get("keep_weekly", 4)
        keep_monthly = request.get("keep_monthly", 6)
        keep_yearly = request.get("keep_yearly", 1)
        dry_run = request.get("dry_run", False)

        # Run prune
        prune_result = await borg.prune_archives(
            repository.path,
            keep_daily=keep_daily,
            keep_weekly=keep_weekly,
            keep_monthly=keep_monthly,
            keep_yearly=keep_yearly,
            dry_run=dry_run,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )

        # Update archive count after successful prune (not dry run)
        if not dry_run and prune_result.get("success"):
            try:
                # List archives to get updated count
                list_result = await borg.list_archives(
                    repository.path,
                    remote_path=repository.remote_path,
                    passphrase=repository.passphrase
                )
                if list_result.get("success"):
                    try:
                        # Parse JSON stdout
                        archives_data = json.loads(list_result.get("stdout", "{}"))
                        if isinstance(archives_data, dict):
                            archive_count = len(archives_data.get("archives", []))
                            repository.archive_count = archive_count
                            db.commit()
                            logger.info("Updated archive count after prune", repository=repository.name, count=archive_count)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse archive list after prune")
            except Exception as e:
                logger.warning("Failed to update archive count after prune", error=str(e))

        return {
            "success": True,
            "dry_run": dry_run,
            "prune_result": prune_result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to prune repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to prune repository: {str(e)}")

@router.get("/{repo_id}/stats")
async def get_repository_statistics(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get repository statistics"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Get detailed statistics
        stats = await get_repository_stats(repository.path)
        
        return {
            "success": True,
            "stats": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get repository statistics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get repository statistics: {str(e)}")

async def check_remote_borg_installation(host: str, username: str, port: int, ssh_key_id: int) -> Dict[str, Any]:
    """Check if borg is installed on remote machine"""
    temp_key_file = None
    try:
        logger.info("Checking remote borg installation", host=host, username=username, port=port)

        # Get SSH key from database
        from app.database.models import SSHKey
        from app.database.database import get_db
        from cryptography.fernet import Fernet
        import base64
        import tempfile

        db = next(get_db())
        ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
        if not ssh_key:
            return {
                "success": False,
                "error": "SSH key not found",
                "has_borg": False
            }

        # Decrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

        # Ensure private key ends with newline
        if not private_key.endswith('\n'):
            private_key += '\n'

        # Create temporary key file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(private_key)
            temp_key_file = f.name

        os.chmod(temp_key_file, 0o600)

        # Check for borg
        borg_cmd = [
            "ssh", "-i", temp_key_file,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-p", str(port),
            f"{username}@{host}",
            "which borg"
        ]

        borg_process = await asyncio.create_subprocess_exec(
            *borg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        borg_stdout, borg_stderr = await asyncio.wait_for(borg_process.communicate(), timeout=15)
        has_borg = borg_process.returncode == 0

        logger.info("Remote borg check completed",
                   host=host,
                   has_borg=has_borg)

        return {
            "success": True,
            "has_borg": has_borg,
            "borg_path": borg_stdout.decode().strip() if has_borg else None
        }

    except asyncio.TimeoutError:
        logger.error("Remote borg check timed out", host=host)
        return {
            "success": False,
            "error": "Connection timeout while checking remote borg installation",
            "has_borg": False
        }
    except Exception as e:
        logger.error("Failed to check remote borg installation", host=host, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "has_borg": False
        }
    finally:
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
            except Exception as e:
                logger.warning("Failed to clean up temp SSH key", error=str(e))

async def verify_existing_repository(path: str, passphrase: str = None, ssh_key_id: int = None, remote_path: str = None) -> Dict[str, Any]:
    """Verify an existing Borg repository by running borg info"""
    temp_key_file = None
    try:
        logger.info("Verifying existing repository", path=path, has_passphrase=bool(passphrase))

        # Build borg info command
        cmd = ["borg", "info", "--json"]

        # Add remote-path if specified
        if remote_path:
            cmd.extend(["--remote-path", remote_path])

        # Set up environment
        env = os.environ.copy()
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase
        env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"

        # Handle SSH key for remote repositories
        if ssh_key_id and path.startswith("ssh://"):
            logger.info("Repository is SSH type, loading SSH key", ssh_key_id=ssh_key_id)

            # Get SSH key from database
            from app.database.models import SSHKey
            from app.database.database import get_db
            from cryptography.fernet import Fernet
            import base64
            import tempfile

            db = next(get_db())
            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
            if not ssh_key:
                return {
                    "success": False,
                    "error": "SSH key not found"
                }

            # Decrypt private key
            encryption_key = settings.secret_key.encode()[:32]
            cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
            private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

            # Create temporary key file
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write(private_key)
                temp_key_file = f.name

            os.chmod(temp_key_file, 0o600)

            # Set SSH key environment variable
            borg_rsh = f"ssh -i {temp_key_file} -o StrictHostKeyChecking=no"
            env["BORG_RSH"] = borg_rsh

        # Add repository path
        cmd.append(path)

        # Execute command
        logger.info("Executing borg info command", command=" ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        stdout_str = stdout.decode() if stdout else ""
        stderr_str = stderr.decode() if stderr else ""

        if process.returncode == 0:
            # Parse JSON output
            try:
                repo_info = json.loads(stdout_str)
                logger.info("Repository verification successful",
                           path=path,
                           encryption=repo_info.get("encryption", {}).get("mode"),
                           archive_count=len(repo_info.get("archives", [])))
                return {
                    "success": True,
                    "info": repo_info
                }
            except json.JSONDecodeError as e:
                logger.error("Failed to parse borg info output", error=str(e))
                return {
                    "success": False,
                    "error": f"Failed to parse repository info: {str(e)}"
                }
        else:
            logger.error("Repository verification failed",
                        returncode=process.returncode,
                        stderr=stderr_str)
            return {
                "success": False,
                "error": stderr_str if stderr_str else "Repository verification failed"
            }

    except asyncio.TimeoutError:
        logger.error("Repository verification timed out", path=path)
        return {
            "success": False,
            "error": "Repository verification timed out"
        }
    except Exception as e:
        logger.error("Failed to verify repository", path=path, error=str(e))
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        # Clean up temporary SSH key file
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
            except Exception as e:
                logger.warning("Failed to clean up temp SSH key", error=str(e))

async def initialize_borg_repository(path: str, encryption: str, passphrase: str = None, ssh_key_id: int = None) -> Dict[str, Any]:
    """Initialize a new Borg repository"""
    temp_key_file = None
    try:
        logger.info("Starting repository initialization",
                   path=path,
                   encryption=encryption,
                   has_passphrase=bool(passphrase),
                   ssh_key_id=ssh_key_id)

        # Check if borg is available locally
        try:
            # Test if borg command exists
            test_process = await asyncio.create_subprocess_exec(
                "borg", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            borg_stdout, borg_stderr = await test_process.communicate()
            if test_process.returncode != 0:
                raise FileNotFoundError("borg command not found")
            logger.info("Borg version check passed", version=borg_stdout.decode().strip())
        except (FileNotFoundError, OSError) as e:
            logger.error("Borg not available", error=str(e))
            return {
                "success": False,
                "error": f"Borg not available on this system: {str(e)}"
            }

        # Build borg init command
        cmd = ["borg", "init", "--encryption", encryption]
        logger.info("Built borg init command", command=" ".join(cmd))

        # Set up environment
        env = os.environ.copy()
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase
            logger.info("Passphrase added to environment")
        # Allow non-interactive access to unencrypted repositories
        env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"

        # Handle SSH key for remote repositories
        if ssh_key_id and path.startswith("ssh://"):
            logger.info("Repository is SSH type, loading SSH key", ssh_key_id=ssh_key_id, path=path)

            # Get SSH key from database
            from app.database.models import SSHKey
            from app.database.database import get_db
            from cryptography.fernet import Fernet
            import base64

            db = next(get_db())
            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
            if not ssh_key:
                logger.error("SSH key not found in database", ssh_key_id=ssh_key_id)
                return {
                    "success": False,
                    "error": "SSH key not found"
                }

            logger.info("SSH key found", name=ssh_key.name, fingerprint=ssh_key.fingerprint[:20] + "...")

            # Decrypt private key
            encryption_key = settings.secret_key.encode()[:32]
            cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
            private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()
            logger.info("SSH private key decrypted successfully")

            # Create temporary key file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write(private_key)
                temp_key_file = f.name

            logger.info("Created temporary SSH key file", path=temp_key_file)

            # Set restrictive permissions on private key file (required by SSH)
            os.chmod(temp_key_file, 0o600)
            logger.info("Set SSH key file permissions to 600")

            # Set SSH key environment variable
            borg_rsh = f"ssh -i {temp_key_file} -o StrictHostKeyChecking=no"
            env["BORG_RSH"] = borg_rsh
            logger.info("Set BORG_RSH environment variable", borg_rsh=borg_rsh)

        # Add repository path
        cmd.append(path)
        logger.info("Full borg init command prepared", command=" ".join(cmd), path=path)

        # Execute command
        logger.info("Executing borg init command...")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        stdout_str = stdout.decode() if stdout else ""
        stderr_str = stderr.decode() if stderr else ""

        logger.info("Borg init command completed",
                   returncode=process.returncode,
                   stdout=stdout_str[:500] if stdout_str else "(empty)",
                   stderr=stderr_str[:500] if stderr_str else "(empty)")

        if process.returncode == 0:
            logger.info("Repository initialized successfully", path=path)
            return {
                "success": True,
                "message": "Repository initialized successfully",
                "already_existed": False
            }
        else:
            # Check if repository already exists (borg returns exit code 2)
            if process.returncode == 2 and "repository already exists" in stderr_str.lower():
                logger.info("Repository already exists at path, treating as success", path=path)
                return {
                    "success": True,
                    "message": "Repository already exists at this location",
                    "already_existed": True
                }

            logger.error("Repository initialization failed",
                        returncode=process.returncode,
                        stderr=stderr_str,
                        stdout=stdout_str)
            return {
                "success": False,
                "error": stderr_str if stderr_str else "Unknown error"
            }
    except Exception as e:
        logger.error("Failed to initialize repository",
                    error=str(e),
                    error_type=type(e).__name__,
                    path=path)
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        # Clean up temporary SSH key file
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
                logger.info("Cleaned up temporary SSH key file", path=temp_key_file)
            except Exception as e:
                logger.warning("Failed to clean up temporary SSH key file",
                             path=temp_key_file,
                             error=str(e))

@router.get("/{repo_id}/archives")
@with_repository_lock('repo_id')
async def list_repository_archives(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all archives in a repository using borg list"""
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            repository = db.query(Repository).filter(Repository.id == repo_id).first()
            if not repository:
                raise HTTPException(status_code=404, detail="Repository not found")

            # Build borg list command
            cmd = ["borg", "list"]

            # Add remote-path if specified
            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])

            cmd.extend(["--json", repository.path])

            # Set up environment with proper lock configuration
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR"
            ]
            env = setup_borg_env(
                passphrase=repository.passphrase,
                ssh_opts=ssh_opts
            )

            # Execute command with increased timeout to match BORG_LOCK_WAIT
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=200)

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"

                # Check if it's a lock timeout error and we have retries left
                if "lock" in error_msg.lower() and "timeout" in error_msg.lower() and attempt < max_retries - 1:
                    logger.warning(f"Lock timeout on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s",
                                 repo_id=repo_id, error=error_msg)
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue

                logger.error("Failed to list archives", error=error_msg)
                raise HTTPException(status_code=500, detail=f"Failed to list archives: {error_msg}")

            # Success - break out of retry loop
            break

        except HTTPException:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Error on attempt {attempt + 1}/{max_retries}, retrying", repo_id=repo_id, error=str(e))
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error("Failed to list archives after retries", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to list archives: {str(e)}")

    # Parse JSON output
    try:
        archives_data = json.loads(stdout.decode())
        archives = archives_data.get("archives", [])

        logger.info("Archives listed successfully", repo_id=repo_id, count=len(archives))

        return {
            "success": True,
            "archives": archives,
            "repository": {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path
            }
        }
    except json.JSONDecodeError as e:
        logger.error("Failed to parse borg list output", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to parse archive list")

@router.get("/{repo_id}/info")
@with_repository_lock('repo_id')
async def get_repository_info(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed repository information using borg info"""
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            repository = db.query(Repository).filter(Repository.id == repo_id).first()
            if not repository:
                raise HTTPException(status_code=404, detail="Repository not found")

            # Build borg info command
            cmd = ["borg", "info"]

            # Add remote-path if specified
            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])

            cmd.extend(["--json", repository.path])

            # Set up environment with proper lock configuration
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR"
            ]
            env = setup_borg_env(
                passphrase=repository.passphrase,
                ssh_opts=ssh_opts
            )

            # Execute command with increased timeout to match BORG_LOCK_WAIT
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=200)

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"

                # Check if it's a lock timeout error and we have retries left
                if "lock" in error_msg.lower() and "timeout" in error_msg.lower() and attempt < max_retries - 1:
                    logger.warning(f"Lock timeout on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s",
                                 repo_id=repo_id, error=error_msg)
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue

                logger.error("Failed to get repository info", error=error_msg)
                raise HTTPException(status_code=500, detail=f"Failed to get repository info: {error_msg}")

            # Success - break out of retry loop
            break

        except HTTPException:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Error on attempt {attempt + 1}/{max_retries}, retrying", repo_id=repo_id, error=str(e))
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error("Failed to get repository info after retries", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to get repository info: {str(e)}")

    # Parse JSON output
    try:
        info_data = json.loads(stdout.decode())

        # Extract relevant information
        repository_info = info_data.get("repository", {})
        cache_info = info_data.get("cache", {})
        encryption_info = info_data.get("encryption", {})

        logger.info("Repository info retrieved successfully", repo_id=repo_id)

        return {
            "success": True,
            "info": {
                "repository": repository_info,
                "cache": cache_info,
                "encryption": encryption_info
            },
            "raw_output": info_data
        }
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse borg info output", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to parse repository info")
    except Exception as e:
        logger.error("Failed to get repository info", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get repository info: {str(e)}")

@router.get("/{repo_id}/archives/{archive_name}/info")
@with_repository_lock('repo_id')
async def get_archive_info(
    repo_id: int,
    archive_name: str,
    include_files: bool = Query(default=True, description="Include file listing in response"),
    file_limit: int = Query(default=1000, description="Maximum number of files to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed archive information using borg info repo::archive with optional file listing"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Build borg info command with repo::archive format
        archive_path = f"{repository.path}::{archive_name}"
        cmd = ["borg", "info"]

        # Add remote-path if specified
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])

        cmd.extend(["--json", archive_path])

        # Set up environment with proper lock configuration
        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR"
        ]
        env = setup_borg_env(
            passphrase=repository.passphrase,
            ssh_opts=ssh_opts
        )

        # Execute command with increased timeout to match BORG_LOCK_WAIT
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=200)

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error("Failed to get archive info", archive_name=archive_name, error=error_msg)
            raise HTTPException(status_code=500, detail=f"Failed to get archive info: {error_msg}")

        # Parse JSON output
        info_data = json.loads(stdout.decode())

        # Extract archive-specific information
        # The output structure for borg info repo::archive includes archives array
        archives_list = info_data.get("archives", [])
        archive_info = archives_list[0] if archives_list else {}

        repository_info = info_data.get("repository", {})
        cache_info = info_data.get("cache", {})
        encryption_info = info_data.get("encryption", {})

        # Optionally fetch file listing using borg list
        if include_files:
            list_cmd = ["borg", "list"]
            if repository.remote_path:
                list_cmd.extend(["--remote-path", repository.remote_path])
            list_cmd.extend(["--json-lines", archive_path])

            # Use same environment setup
            list_env = os.environ.copy()
            if repository.passphrase:
                list_env["BORG_PASSPHRASE"] = repository.passphrase
            list_env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"

            # Add SSH options
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR"
            ]
            list_env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            try:
                list_process = await asyncio.create_subprocess_exec(
                    *list_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=list_env
                )
                list_stdout, list_stderr = await asyncio.wait_for(list_process.communicate(), timeout=60)

                if list_process.returncode == 0:
                    # Parse JSON-lines output
                    files = []
                    for line in list_stdout.decode().strip().split('\n'):
                        if line and len(files) < file_limit:
                            try:
                                file_obj = json.loads(line)
                                files.append({
                                    "path": file_obj.get("path"),
                                    "type": file_obj.get("type"),
                                    "mode": file_obj.get("mode"),
                                    "user": file_obj.get("user"),
                                    "group": file_obj.get("group"),
                                    "size": file_obj.get("size"),
                                    "mtime": file_obj.get("mtime"),
                                    "healthy": file_obj.get("healthy", True)
                                })
                            except json.JSONDecodeError:
                                continue
                    archive_info["files"] = files
                    archive_info["file_count"] = len(files)
                    logger.info("Fetched file listing for archive",
                               archive_name=archive_name,
                               file_count=len(files))
                else:
                    logger.warning("Failed to fetch file listing",
                                 archive_name=archive_name,
                                 error=list_stderr.decode())
                    archive_info["files"] = []
                    archive_info["file_count"] = 0
            except Exception as e:
                logger.warning("Error fetching file listing",
                             archive_name=archive_name,
                             error=str(e))
                archive_info["files"] = []
                archive_info["file_count"] = 0

        logger.info("Archive info retrieved successfully",
                   repo_id=repo_id,
                   archive_name=archive_name,
                   include_files=include_files)

        return {
            "success": True,
            "archive": archive_info,
            "repository": repository_info,
            "cache": cache_info,
            "encryption": encryption_info,
            "raw_output": info_data
        }
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse borg info output", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to parse archive info")
    except Exception as e:
        logger.error("Failed to get archive info", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get archive info: {str(e)}")

@router.get("/{repo_id}/archives/{archive_name}/files")
async def list_archive_files(
    repo_id: int,
    archive_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: Optional[int] = Query(None, description="Limit number of files returned")
):
    """List files in an archive using borg list repo::archive"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Build borg list command with repo::archive format
        archive_path = f"{repository.path}::{archive_name}"
        cmd = ["borg", "list"]

        # Add remote-path if specified
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])

        # Use --json-lines for file listing
        cmd.extend(["--json-lines", archive_path])

        # Set up environment with proper lock configuration
        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR"
        ]
        env = setup_borg_env(
            passphrase=repository.passphrase,
            ssh_opts=ssh_opts
        )

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error("Failed to list archive files", archive_name=archive_name, error=error_msg)
            raise HTTPException(status_code=500, detail=f"Failed to list archive files: {error_msg}")

        # Parse JSON-lines output (one JSON object per line)
        files = []
        for line in stdout.decode().strip().split('\n'):
            if line:
                try:
                    file_obj = json.loads(line)
                    files.append({
                        "path": file_obj.get("path"),
                        "type": file_obj.get("type"),  # 'd' for directory, '-' for file
                        "mode": file_obj.get("mode"),
                        "user": file_obj.get("user"),
                        "group": file_obj.get("group"),
                        "size": file_obj.get("size"),
                        "mtime": file_obj.get("mtime"),
                        "healthy": file_obj.get("healthy", True)
                    })
                except json.JSONDecodeError:
                    continue

        # Apply limit if specified
        if limit and limit > 0:
            files = files[:limit]

        logger.info("Archive files listed successfully",
                   repo_id=repo_id,
                   archive_name=archive_name,
                   file_count=len(files))

        return {
            "success": True,
            "files": files,
            "total_count": len(files),
            "archive_name": archive_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list archive files", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list archive files: {str(e)}")

async def get_repository_stats(path: str) -> Dict[str, Any]:
    """Get repository statistics"""
    try:
        # Get repository info
        info_result = await borg._execute_command(["borg", "info", path])

        if not info_result["success"]:
            return {
                "error": "Failed to get repository info",
                "details": info_result["stderr"]
            }

        # Parse repository info (basic implementation)
        # In a real implementation, you would parse the borg info output
        stats = {
            "total_size": "Unknown",
            "compressed_size": "Unknown",
            "deduplicated_size": "Unknown",
            "archive_count": 0,
            "last_modified": None,
            "encryption": "Unknown"
        }

        # Try to get archive count
        archives_result = await borg.list_archives(path)
        if archives_result["success"]:
            try:
                archives_data = archives_result["stdout"]
                if archives_data:
                    stats["archive_count"] = len(archives_data)
            except:
                pass

        return stats
    except Exception as e:
        logger.error("Failed to get repository stats", error=str(e))
        return {
            "error": str(e)
        }

@router.post("/{repository_id}/break-lock")
async def break_repository_lock(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Break a stale lock on a repository

    Use this when a backup has crashed or been killed, leaving behind a lock file
    that prevents new backups from starting.

    WARNING: Only use this if you're CERTAIN no backup is currently running!
    """
    try:
        # Get repository from database
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        logger.info("Breaking repository lock",
                   repository=repository.path,
                   user=current_user.username,
                   repository_id=repository_id)

        # Set up environment with SSH options and passphrase
        env = os.environ.copy()

        # Add SSH options
        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR"
        ]
        env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

        # Add passphrase if available
        if repository.passphrase:
            env['BORG_PASSPHRASE'] = repository.passphrase

        # Skip prompts
        env['BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK'] = 'yes'
        env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'

        # Build borg break-lock command
        cmd = ["borg", "break-lock", repository.path]

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
        stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""

        if process.returncode == 0:
            logger.info("Successfully broke repository lock",
                       repository=repository.path,
                       user=current_user.username)
            return {
                "success": True,
                "message": "Lock successfully removed. You can now start a new backup.",
                "repository": repository.path,
                "output": stdout_str
            }
        else:
            logger.error("Failed to break repository lock",
                        repository=repository.path,
                        returncode=process.returncode,
                        stderr=stderr_str)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to break lock: {stderr_str}"
            )

    except asyncio.TimeoutError:
        logger.error("Timeout breaking repository lock", repository_id=repository_id)
        raise HTTPException(
            status_code=500,
            detail="Timeout while trying to break lock"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error breaking repository lock",
                    repository_id=repository_id,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to break lock: {str(e)}"
        )
