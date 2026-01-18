from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import structlog
import os
import subprocess
import asyncio
import json

from app.database.database import get_db
from app.database.models import User, Repository, CheckJob, CompactJob, PruneJob
from app.core.security import get_current_user
from app.core.borg import BorgInterface
from app.config import settings
from app.services.check_service import check_service
from app.services.compact_service import compact_service
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(tags=["repositories"])

# Initialize Borg interface
borg = BorgInterface()

# Helper function to get standard SSH options
def get_standard_ssh_opts(include_key_path=None):
    """Get standardized SSH options for Borg operations

    Args:
        include_key_path: Optional path to SSH private key file

    Returns:
        List of SSH options for use with BORG_RSH
    """
    opts = []

    if include_key_path:
        opts.extend(["-i", include_key_path])

    opts.extend([
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "RequestTTY=no",  # Disable TTY allocation to prevent shell initialization output (fixes Aurora Linux)
        "-o", "PermitLocalCommand=no"  # Prevent local command execution
    ])

    return opts

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

# Helper function to update repository archive count
async def update_repository_stats(repository: Repository, db: Session) -> bool:
    """
    Update the archive count and repository size stats by querying Borg.
    Returns True if successful, False otherwise.
    """
    try:
        # Get archive list and count
        list_result = await borg.list_archives(
            repository.path,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )

        archive_count = 0
        total_size = None

        if list_result.get("success"):
            try:
                archives_data = json.loads(list_result.get("stdout", "{}"))
                if isinstance(archives_data, dict):
                    # Get archive count
                    archive_count = len(archives_data.get("archives", []))
            except json.JSONDecodeError as e:
                logger.error("Failed to parse archive list JSON",
                           repository=repository.name,
                           error=str(e),
                           stdout=list_result.get("stdout", "")[:200])

        # Get repository size from borg info (includes cache stats)
        # Use direct command execution with proper passphrase handling
        cmd = ["borg", "info"]
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])
        cmd.extend([repository.path, "--json"])

        env = setup_borg_env(
            passphrase=repository.passphrase,
            ssh_opts=get_standard_ssh_opts()
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.borg_info_timeout)

            if process.returncode == 0:
                info_data = json.loads(stdout.decode())
                cache = info_data.get("cache", {}).get("stats", {})
                if cache:
                    unique_csize = cache.get("unique_csize", 0)
                    if unique_csize > 0:
                        total_size = format_bytes(unique_csize)
        except Exception as e:
            logger.warning("Failed to get repository size from borg info",
                         repository=repository.name,
                         error=str(e))

        # Update repository
        old_count = repository.archive_count
        old_size = repository.total_size
        repository.archive_count = archive_count
        if total_size:
            repository.total_size = total_size

        db.commit()
        logger.info("Updated repository stats",
                  repository=repository.name,
                  archive_count_old=old_count,
                  archive_count_new=archive_count,
                  size_old=old_size,
                  size_new=total_size)
        return True

    except Exception as e:
        logger.error("Exception while updating repository stats",
                   repository=repository.name,
                   error=str(e))
        return False

# Helper function to format bytes to human readable format
def format_bytes(bytes_size: int) -> str:
    """Format bytes to human readable string (e.g., '1.23 GB')"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} EB"

# Helper function to format datetime with timezone
def format_datetime(dt):
    """Format datetime to ISO8601 with UTC timezone indicator"""
    return serialize_datetime(dt)

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
    hook_timeout: Optional[int] = 300  # Hook timeout in seconds (legacy, use pre/post_hook_timeout)
    pre_hook_timeout: Optional[int] = 300  # Pre-backup hook timeout in seconds
    post_hook_timeout: Optional[int] = 300  # Post-backup hook timeout in seconds
    continue_on_hook_failure: Optional[bool] = False  # Continue backup if pre-hook fails
    mode: str = "full"  # full: backups + observability, observe: observability-only
    custom_flags: Optional[str] = None  # Custom command-line flags for borg create (e.g., "--stats --list")
    source_connection_id: Optional[int] = None  # SSH connection ID for remote data source (pull-based backups)

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
    hook_timeout: Optional[int] = 300  # Hook timeout in seconds (legacy, use pre/post_hook_timeout)
    pre_hook_timeout: Optional[int] = 300  # Pre-backup hook timeout in seconds
    post_hook_timeout: Optional[int] = 300  # Post-backup hook timeout in seconds
    continue_on_hook_failure: Optional[bool] = False  # Continue backup if pre-hook fails
    mode: str = "full"  # full: backups + observability, observe: observability-only
    custom_flags: Optional[str] = None  # Custom command-line flags for borg create (e.g., "--stats --list")
    source_connection_id: Optional[int] = None  # SSH connection ID for remote data source (pull-based backups)

class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    compression: Optional[str] = None
    source_directories: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    remote_path: Optional[str] = None
    pre_backup_script: Optional[str] = None
    post_backup_script: Optional[str] = None
    hook_timeout: Optional[int] = None  # Legacy, use pre/post_hook_timeout
    pre_hook_timeout: Optional[int] = None
    post_hook_timeout: Optional[int] = None
    continue_on_hook_failure: Optional[bool] = None
    mode: Optional[str] = None  # full: backups + observability, observe: observability-only
    custom_flags: Optional[str] = None  # Custom command-line flags for borg create
    source_connection_id: Optional[int] = None  # SSH connection ID for remote data source

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

        # Check for running maintenance jobs for each repository
        repo_list = []
        for repo in repositories:
            # Check if this repository has running check, compact, or prune jobs
            has_check = db.query(CheckJob).filter(
                CheckJob.repository_id == repo.id,
                CheckJob.status == "running"
            ).first() is not None

            has_compact = db.query(CompactJob).filter(
                CompactJob.repository_id == repo.id,
                CompactJob.status == "running"
            ).first() is not None

            has_prune = db.query(PruneJob).filter(
                PruneJob.repository_id == repo.id,
                PruneJob.status == "running"
            ).first() is not None

            repo_list.append({
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "encryption": repo.encryption,
                "compression": repo.compression,
                "source_directories": json.loads(repo.source_directories) if repo.source_directories else [],
                "exclude_patterns": json.loads(repo.exclude_patterns) if repo.exclude_patterns else [],
                "repository_type": repo.repository_type,
                "host": repo.host,
                "port": repo.port,
                "username": repo.username,
                "ssh_key_id": repo.ssh_key_id,
                "remote_path": repo.remote_path,
                "last_backup": format_datetime(repo.last_backup),
                "last_check": format_datetime(repo.last_check),
                "last_compact": format_datetime(repo.last_compact),
                "total_size": repo.total_size,
                "archive_count": repo.archive_count,
                "created_at": format_datetime(repo.created_at),
                "updated_at": format_datetime(repo.updated_at),
                "pre_backup_script": repo.pre_backup_script,
                "post_backup_script": repo.post_backup_script,
                "hook_timeout": repo.hook_timeout,
                "pre_hook_timeout": repo.pre_hook_timeout,
                "post_hook_timeout": repo.post_hook_timeout,
                "continue_on_hook_failure": repo.continue_on_hook_failure,
                "mode": repo.mode or "full",  # Default to "full" for backward compatibility
                "custom_flags": repo.custom_flags,
                "has_running_maintenance": has_check or has_compact or has_prune
            })

        return {
            "success": True,
            "repositories": repo_list
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
        # Validate source directories are provided (only for full mode repositories)
        if repo_data.mode == "full":
            if not repo_data.source_directories or len(repo_data.source_directories) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="At least one source directory is required for full mode repositories. Source directories specify what data will be backed up to this repository."
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
            # But first check if path looks like an SSH URL
            if repo_path.startswith("ssh://"):
                raise HTTPException(
                    status_code=400,
                    detail="Path appears to be an SSH URL but repository_type is 'local'. Please set repository_type to 'ssh'."
                )

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

            # Note: We don't check if borg is installed on the remote machine.
            # Some SSH hosts (like Hetzner Storagebox) use restricted shells that block
            # diagnostic commands like "which borg", but Borg commands still work.
            # If Borg is truly not installed, the borg init command will fail with a clear error.
            logger.info("Skipping remote borg check for SSH repository",
                       host=repo_data.host,
                       username=repo_data.username)

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
            repo_data.ssh_key_id if repo_data.repository_type in ["ssh", "sftp"] else None,
            repo_data.remote_path
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
            pre_hook_timeout=repo_data.pre_hook_timeout,
            post_hook_timeout=repo_data.post_hook_timeout,
            continue_on_hook_failure=repo_data.continue_on_hook_failure,
            mode=repo_data.mode,
            custom_flags=repo_data.custom_flags,
            source_ssh_connection_id=repo_data.source_connection_id
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
        # Validate source directories are provided (only for full mode repositories)
        if repo_data.mode == "full":
            if not repo_data.source_directories or len(repo_data.source_directories) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="At least one source directory is required for full mode repositories. Source directories specify what data will be backed up to this repository."
                )

        # Validate repository type and path
        repo_path = repo_data.path.strip()

        if repo_data.repository_type == "local":
            # For local repositories, ensure path is absolute
            # But first check if path looks like an SSH URL
            if repo_path.startswith("ssh://"):
                raise HTTPException(
                    status_code=400,
                    detail="Path appears to be an SSH URL but repository_type is 'local'. Please set repository_type to 'ssh'."
                )

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

            # Note: We don't check if borg is installed on the remote machine.
            # Some SSH hosts (like Hetzner Storagebox) use restricted shells that block
            # diagnostic commands like "which borg", but Borg commands still work.
            # If Borg is truly not installed, the borg info command will fail with a clear error.
            logger.info("Skipping remote borg check for SSH repository",
                       host=repo_data.host,
                       username=repo_data.username)

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
        # Note: archive_count will be updated after creation via borg list
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
            archive_count=0,  # Will be updated below
            pre_backup_script=repo_data.pre_backup_script,
            post_backup_script=repo_data.post_backup_script,
            hook_timeout=repo_data.hook_timeout,
            pre_hook_timeout=repo_data.pre_hook_timeout,
            post_hook_timeout=repo_data.post_hook_timeout,
            continue_on_hook_failure=repo_data.continue_on_hook_failure,
            mode=repo_data.mode,
            custom_flags=repo_data.custom_flags,
            source_ssh_connection_id=repo_data.source_connection_id
        )

        db.add(repository)
        db.commit()
        db.refresh(repository)

        # Update archive count by listing archives (non-blocking - don't fail import)
        try:
            await update_repository_stats(repository, db)
        except Exception as e:
            # Log but don't fail the import - stats can be updated later
            logger.warning("Failed to update repository stats after import",
                         repository=repository.name,
                         error=str(e))

        logger.info("Repository imported successfully",
                   name=repo_data.name,
                   path=repo_path,
                   user=current_user.username)

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

@router.post("/{repo_id}/keyfile")
async def upload_keyfile(
    repo_id: int,
    keyfile: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a keyfile for a repository that uses keyfile or keyfile-blake2 encryption.

    This endpoint allows uploading keyfiles for existing repositories that were created
    elsewhere and use keyfile-based encryption modes.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Get repository
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Verify repository uses keyfile encryption
        if repository.encryption not in ["keyfile", "keyfile-blake2"]:
            raise HTTPException(
                status_code=400,
                detail=f"Repository uses '{repository.encryption}' encryption, which doesn't require a keyfile. "
                       f"Keyfile upload is only needed for 'keyfile' or 'keyfile-blake2' encryption modes."
            )

        # Validate keyfile content
        content = await keyfile.read()
        if not content:
            raise HTTPException(status_code=400, detail="Keyfile is empty")

        # Extract repository ID from repository path to generate keyfile name
        # Borg uses the repository ID in keyfile names
        import re
        import hashlib

        # For local paths: generate a simple filename
        # For SSH paths: extract host and path
        safe_name = re.sub(r'[^\w\-_.]', '_', repository.path)
        keyfile_name = f"{safe_name}.key"

        # Store keyfile in /data/borg_keys/
        keyfile_dir = os.path.join(settings.data_dir, "borg_keys")
        os.makedirs(keyfile_dir, exist_ok=True)

        keyfile_path = os.path.join(keyfile_dir, keyfile_name)

        # Write keyfile
        with open(keyfile_path, 'wb') as f:
            f.write(content)

        # Set proper permissions (600 - owner read/write only)
        os.chmod(keyfile_path, 0o600)

        # Update repository to indicate it has a keyfile
        repository.has_keyfile = True
        db.commit()

        logger.info("Keyfile uploaded successfully",
                   repo_id=repo_id,
                   repo_name=repository.name,
                   keyfile_path=keyfile_path)

        return {
            "success": True,
            "message": "Keyfile uploaded successfully",
            "keyfile_name": keyfile_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload keyfile", repo_id=repo_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to upload keyfile: {str(e)}")

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

        if repo_data.pre_hook_timeout is not None:
            repository.pre_hook_timeout = repo_data.pre_hook_timeout

        if repo_data.post_hook_timeout is not None:
            repository.post_hook_timeout = repo_data.post_hook_timeout

        if repo_data.continue_on_hook_failure is not None:
            repository.continue_on_hook_failure = repo_data.continue_on_hook_failure

        if repo_data.mode is not None:
            # Validate source directories when switching to full mode
            if repo_data.mode == "full" and (not repository.source_directories or repository.source_directories == "[]"):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot switch to full mode: at least one source directory is required"
                )
            repository.mode = repo_data.mode
            # If switching to observe mode, log it
            if repo_data.mode == "observe":
                logger.info("Repository switched to observability-only mode", repo_id=repo_id)

        if repo_data.custom_flags is not None:
            repository.custom_flags = repo_data.custom_flags

        if repo_data.source_connection_id is not None:
            repository.source_ssh_connection_id = repo_data.source_connection_id

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
    request: dict = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a background check job for repository integrity"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Check if there's already a running check job for this repository
        running_job = db.query(CheckJob).filter(
            CheckJob.repository_id == repo_id,
            CheckJob.status == "running"
        ).first()

        if running_job:
            raise HTTPException(
                status_code=409,
                detail=f"A check operation is already running for this repository (Job ID: {running_job.id})"
            )

        # Extract max_duration from request body (default to 3600)
        max_duration = request.get("max_duration", 3600) if request else 3600

        # Create check job record
        check_job = CheckJob(
            repository_id=repo_id,
            status="pending",
            max_duration=max_duration
        )
        db.add(check_job)
        db.commit()
        db.refresh(check_job)

        # Execute check asynchronously (non-blocking)
        asyncio.create_task(
            check_service.execute_check(
                check_job.id,
                repo_id,
                db
            )
        )

        logger.info("Check job created", job_id=check_job.id, repository_id=repo_id, user=current_user.username)

        return {
            "job_id": check_job.id,
            "status": "pending",
            "message": "Check job started"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start check job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start check: {str(e)}")

@router.post("/{repo_id}/compact")
async def compact_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a background compact job to free space"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Check if there's already a running compact job for this repository
        running_job = db.query(CompactJob).filter(
            CompactJob.repository_id == repo_id,
            CompactJob.status == "running"
        ).first()

        if running_job:
            raise HTTPException(
                status_code=409,
                detail=f"A compact operation is already running for this repository (Job ID: {running_job.id})"
            )

        # Create compact job record
        compact_job = CompactJob(
            repository_id=repo_id,
            repository_path=repository.path,  # Capture path for display
            status="pending",
            scheduled_compact=False  # Manual trigger
        )
        db.add(compact_job)
        db.commit()
        db.refresh(compact_job)

        # Execute compact asynchronously (non-blocking)
        asyncio.create_task(
            compact_service.execute_compact(
                compact_job.id,
                repo_id,
                db
            )
        )

        logger.info("Compact job created", job_id=compact_job.id, repository_id=repo_id, user=current_user.username)

        return {
            "job_id": compact_job.id,
            "status": "pending",
            "message": "Compact job started"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start compact job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start compact: {str(e)}")

@router.post("/{repo_id}/prune")
async def prune_repository(
    repo_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a background prune job to remove old archives based on retention policy"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Check if there's already a running prune job for this repository
        running_job = db.query(PruneJob).filter(
            PruneJob.repository_id == repo_id,
            PruneJob.status == "running"
        ).first()

        if running_job:
            raise HTTPException(
                status_code=409,
                detail=f"A prune operation is already running for this repository (Job ID: {running_job.id})"
            )

        # Extract retention policy from request
        keep_hourly = request.get("keep_hourly", 0)
        keep_daily = request.get("keep_daily", 7)
        keep_weekly = request.get("keep_weekly", 4)
        keep_monthly = request.get("keep_monthly", 6)
        keep_quarterly = request.get("keep_quarterly", 0)
        keep_yearly = request.get("keep_yearly", 1)
        dry_run = request.get("dry_run", False)

        # Create prune job record
        prune_job = PruneJob(
            repository_id=repo_id,
            repository_path=repository.path,  # Capture path for display
            status="pending",
            scheduled_prune=False  # Manual trigger
        )
        db.add(prune_job)
        db.commit()
        db.refresh(prune_job)

        # Execute prune synchronously and return results
        # (Prune operations are fast enough to wait for completion)
        from app.services.prune_service import prune_service

        logger.info("Starting prune job",
                   job_id=prune_job.id,
                   repository_id=repo_id,
                   dry_run=dry_run,
                   user=current_user.username)

        # Wait for prune to complete and get logs
        await prune_service.execute_prune(
            prune_job.id,
            repo_id,
            keep_hourly,
            keep_daily,
            keep_weekly,
            keep_monthly,
            keep_quarterly,
            keep_yearly,
            dry_run,
            db
        )

        # Refresh job to get updated status and logs
        db.refresh(prune_job)

        # Read log file if it exists
        stdout_output = ""
        stderr_output = ""
        if prune_job.log_file_path and os.path.exists(prune_job.log_file_path):
            try:
                with open(prune_job.log_file_path, 'r') as f:
                    log_content = f.read()
                    # All output goes to stdout for prune
                    stdout_output = log_content
            except Exception as e:
                logger.warning("Failed to read prune log file", error=str(e))
                stderr_output = f"Failed to read log file: {str(e)}"

        # Return results in format expected by frontend
        return {
            "job_id": prune_job.id,
            "status": prune_job.status,
            "dry_run": dry_run,
            "prune_result": {
                "success": prune_job.status == "completed",
                "stdout": stdout_output,
                "stderr": stderr_output if stderr_output or prune_job.error_message else (prune_job.error_message or "")
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start prune job", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start prune: {str(e)}")

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
            ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file)
            env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"

        # Add repository path
        cmd.append(path)

        # Execute command
        logger.info("Executing borg info command", command=" ".join(cmd), timeout=settings.borg_info_timeout)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.borg_info_timeout)
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

async def initialize_borg_repository(path: str, encryption: str, passphrase: str = None, ssh_key_id: int = None, remote_path: str = None) -> Dict[str, Any]:
    """Initialize a new Borg repository"""
    temp_key_file = None
    try:
        logger.info("Starting repository initialization",
                   path=path,
                   encryption=encryption,
                   has_passphrase=bool(passphrase),
                   ssh_key_id=ssh_key_id,
                   remote_path=remote_path)

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

        # Add remote-path argument if specified
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
            logger.info("Added remote-path to borg init command", remote_path=remote_path)

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
            ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file)
            borg_rsh = f"ssh {' '.join(ssh_opts)}"
            env["BORG_RSH"] = borg_rsh
            logger.info("Set BORG_RSH environment variable", borg_rsh=borg_rsh)

        # Add repository path
        cmd.append(path)
        logger.info("Full borg init command prepared", command=" ".join(cmd), path=path)

        # Execute command
        logger.info("Executing borg init command...", timeout=settings.borg_init_timeout)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.borg_init_timeout)
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
async def list_repository_archives(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all archives in a repository using borg list"""
    max_retries = 3
    retry_delay = 1  # seconds - quick retry after breaking lock

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
            ssh_opts = get_standard_ssh_opts()
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

            # Use configurable timeout to allow for large repositories and slow SSH connections
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.borg_list_timeout)

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"

                # Check if it's a lock timeout error - return special error for user prompt
                if "lock" in error_msg.lower() and "timeout" in error_msg.lower():
                    logger.warning(f"Lock timeout detected on attempt {attempt + 1}/{max_retries}",
                                 repo_id=repo_id, error=error_msg)
                    raise HTTPException(
                        status_code=423,  # 423 Locked status code
                        detail={
                            "error": "repository_locked",
                            "message": "Repository is locked by another process or has a stale lock",
                            "suggestion": "If no backup is currently running, this is likely a stale lock. You can break the lock to continue.",
                            "repository_id": repo_id,
                            "can_break_lock": True
                        }
                    )

                logger.error("Failed to list archives", error=error_msg)
                raise HTTPException(status_code=500, detail=f"Failed to list archives: {error_msg}")

            # Success - break out of retry loop
            break

        except HTTPException:
            raise
        except asyncio.TimeoutError:
            error_msg = f"Operation timed out after 200 seconds. This can happen with slow SSH connections or large repositories."
            if attempt < max_retries - 1:
                logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries}, retrying", repo_id=repo_id)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error("Failed to list archives after retries: timeout", repo_id=repo_id)
            raise HTTPException(status_code=504, detail=error_msg)
        except Exception as e:
            error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
            if attempt < max_retries - 1:
                logger.warning(f"Error on attempt {attempt + 1}/{max_retries}, retrying", repo_id=repo_id, error=error_msg)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error("Failed to list archives after retries", error=error_msg, repo_id=repo_id)
            raise HTTPException(status_code=500, detail=f"Failed to list archives: {error_msg}")

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
async def get_repository_info(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed repository information using borg info"""
    max_retries = 3
    retry_delay = 1  # seconds - quick retry after breaking lock

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
            ssh_opts = get_standard_ssh_opts()
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

            # Use configurable timeout to allow for large repositories and slow SSH connections
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.borg_list_timeout)

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"

                # Check if it's a lock timeout error - return special error for user prompt
                if "lock" in error_msg.lower() and "timeout" in error_msg.lower():
                    logger.warning(f"Lock timeout detected on attempt {attempt + 1}/{max_retries}",
                                 repo_id=repo_id, error=error_msg)
                    raise HTTPException(
                        status_code=423,  # 423 Locked status code
                        detail={
                            "error": "repository_locked",
                            "message": "Repository is locked by another process or has a stale lock",
                            "suggestion": "If no backup is currently running, this is likely a stale lock. You can break the lock to continue.",
                            "repository_id": repo_id,
                            "can_break_lock": True
                        }
                    )

                logger.error("Failed to get repository info", error=error_msg)
                raise HTTPException(status_code=500, detail=f"Failed to get repository info: {error_msg}")

            # Success - break out of retry loop
            break

        except HTTPException:
            raise
        except asyncio.TimeoutError:
            error_msg = f"Operation timed out after 200 seconds. This can happen with slow SSH connections or large repositories."
            if attempt < max_retries - 1:
                logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries}, retrying", repo_id=repo_id)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error("Failed to get repository info after retries: timeout", repo_id=repo_id)
            raise HTTPException(status_code=504, detail=error_msg)
        except Exception as e:
            error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
            if attempt < max_retries - 1:
                logger.warning(f"Error on attempt {attempt + 1}/{max_retries}, retrying", repo_id=repo_id, error=error_msg)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error("Failed to get repository info after retries", error=error_msg, repo_id=repo_id)
            raise HTTPException(status_code=500, detail=f"Failed to get repository info: {error_msg}")

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

@router.post("/{repo_id}/break-lock")
async def break_repository_lock(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Break a stale lock on a repository (user-initiated)"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        logger.warning("User requested lock break", repo_id=repo_id, user=current_user.username)

        # Break the lock using borg break-lock
        result = await borg.break_lock(
            repository.path,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )

        if result.get("success"):
            logger.info("Successfully broke repository lock", repo_id=repo_id, user=current_user.username)
            return {
                "success": True,
                "message": "Lock successfully broken. You can now retry your operation."
            }
        else:
            error_msg = result.get("stderr", "Unknown error")
            logger.error("Failed to break lock", repo_id=repo_id, error=error_msg)
            raise HTTPException(status_code=500, detail=f"Failed to break lock: {error_msg}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error breaking repository lock", repo_id=repo_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to break lock: {str(e)}")

@router.get("/{repo_id}/archives/{archive_name}/info")
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

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.borg_info_timeout)

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
            ssh_opts = get_standard_ssh_opts()
            list_env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            try:
                list_process = await asyncio.create_subprocess_exec(
                    *list_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=list_env
                )
                list_stdout, list_stderr = await asyncio.wait_for(list_process.communicate(), timeout=settings.borg_list_timeout)

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

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.borg_list_timeout)

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
        ssh_opts = get_standard_ssh_opts()
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

# Check job endpoints
@router.get("/check-jobs/{job_id}")
async def get_check_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get status of a check job"""
    try:
        job = db.query(CheckJob).filter(CheckJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Check job not found")

        # Read log file if it exists (like prune/compact jobs)
        log_content = ""
        if job.log_file_path and os.path.exists(job.log_file_path):
            try:
                with open(job.log_file_path, 'r') as f:
                    log_content = f.read()
            except Exception as e:
                logger.warning("Failed to read check log file", error=str(e))
                log_content = f"Failed to read log file: {str(e)}"
        elif job.logs:
            # Fallback to old logs field for backwards compatibility
            log_content = job.logs

        return {
            "id": job.id,
            "repository_id": job.repository_id,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "progress": job.progress,
            "progress_message": job.progress_message,
            "error_message": job.error_message,
            "logs": log_content
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get check job status", error=str(e), job_id=job_id)
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")

@router.get("/{repo_id}/check-jobs")
async def get_repository_check_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Get recent check jobs for a repository"""
    try:
        jobs = db.query(CheckJob).filter(
            CheckJob.repository_id == repo_id
        ).order_by(CheckJob.id.desc()).limit(limit).all()

        return {
            "jobs": [
                {
                    "id": job.id,
                    "repository_id": job.repository_id,
                    "status": job.status,
                    "started_at": serialize_datetime(job.started_at),
                    "completed_at": serialize_datetime(job.completed_at),
                    "progress": job.progress,
                    "progress_message": job.progress_message,
                    "error_message": job.error_message,
                    "has_logs": job.has_logs,
                }
                for job in jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get check jobs", error=str(e), repository_id=repo_id)
        raise HTTPException(status_code=500, detail=f"Failed to get check jobs: {str(e)}")

# Compact job endpoints
@router.get("/compact-jobs/{job_id}")
async def get_compact_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get status of a compact job"""
    try:
        job = db.query(CompactJob).filter(CompactJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Compact job not found")

        return {
            "id": job.id,
            "repository_id": job.repository_id,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "progress": job.progress,
            "progress_message": job.progress_message,
            "error_message": job.error_message,
            "logs": job.logs
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get compact job status", error=str(e), job_id=job_id)
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")

@router.get("/{repo_id}/compact-jobs")
async def get_repository_compact_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Get recent compact jobs for a repository"""
    try:
        jobs = db.query(CompactJob).filter(
            CompactJob.repository_id == repo_id
        ).order_by(CompactJob.id.desc()).limit(limit).all()

        return {
            "jobs": [
                {
                    "id": job.id,
                    "repository_id": job.repository_id,
                    "status": job.status,
                    "started_at": serialize_datetime(job.started_at),
                    "completed_at": serialize_datetime(job.completed_at),
                    "progress": job.progress,
                    "progress_message": job.progress_message,
                    "error_message": job.error_message,
                }
                for job in jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to get compact jobs", error=str(e), repository_id=repo_id)
        raise HTTPException(status_code=500, detail=f"Failed to get compact jobs: {str(e)}")

# Helper endpoint to check if repository has running maintenance jobs
@router.get("/{repo_id}/running-jobs")
async def get_running_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if repository has any running check, compact, or prune jobs"""
    try:
        # Force refresh from database to get latest values
        db.expire_all()

        check_job = db.query(CheckJob).filter(
            CheckJob.repository_id == repo_id,
            CheckJob.status == "running"
        ).first()

        compact_job = db.query(CompactJob).filter(
            CompactJob.repository_id == repo_id,
            CompactJob.status == "running"
        ).first()

        prune_job = db.query(PruneJob).filter(
            PruneJob.repository_id == repo_id,
            PruneJob.status == "running"
        ).first()

        result = {
            "has_running_jobs": bool(check_job or compact_job or prune_job),
            "check_job": {
                "id": check_job.id,
                "progress": check_job.progress,
                "progress_message": check_job.progress_message,
                "started_at": serialize_datetime(check_job.started_at)
            } if check_job else None,
            "compact_job": {
                "id": compact_job.id,
                "progress": compact_job.progress,
                "progress_message": compact_job.progress_message,
                "started_at": serialize_datetime(compact_job.started_at)
            } if compact_job else None,
            "prune_job": {
                "id": prune_job.id,
                "started_at": serialize_datetime(prune_job.started_at)
            } if prune_job else None
        }

        logger.info("Running jobs API response", repository_id=repo_id, result=result)

        return result
    except Exception as e:
        logger.error("Failed to get running jobs", error=str(e), repository_id=repo_id)
        raise HTTPException(status_code=500, detail=f"Failed to get running jobs: {str(e)}")

@router.put("/{repo_id}/check-schedule")
async def update_check_schedule(
    repo_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update scheduled check configuration for repository"""
    try:
        from datetime import datetime
        from croniter import croniter

        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Update check schedule settings
        cron_expression = request.get("cron_expression")
        if cron_expression is not None:
            # Set to None if empty string or "disabled"
            if not cron_expression or cron_expression.strip() == "":
                repo.check_cron_expression = None
            else:
                # Validate cron expression
                try:
                    croniter(cron_expression)
                    repo.check_cron_expression = cron_expression
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid cron expression: {str(e)}")

        max_duration = request.get("max_duration")
        if max_duration is not None:
            repo.check_max_duration = max_duration

        notify_on_success = request.get("notify_on_success")
        if notify_on_success is not None:
            repo.notify_on_check_success = notify_on_success

        notify_on_failure = request.get("notify_on_failure")
        if notify_on_failure is not None:
            repo.notify_on_check_failure = notify_on_failure

        # Calculate next check time from cron expression
        if repo.check_cron_expression:
            try:
                base_time = datetime.utcnow()
                cron = croniter(repo.check_cron_expression, base_time)
                repo.next_scheduled_check = cron.get_next(datetime)
            except Exception as e:
                logger.error("Failed to calculate next check time", error=str(e), repo_id=repo_id)
                repo.next_scheduled_check = None
        else:
            # Disabled - clear next scheduled check
            repo.next_scheduled_check = None

        db.commit()
        db.refresh(repo)

        logger.info("Check schedule updated",
                   repo_id=repo_id,
                   cron_expression=repo.check_cron_expression,
                   next_check=repo.next_scheduled_check)

        return {
            "success": True,
            "repository": {
                "id": repo.id,
                "name": repo.name,
                "check_cron_expression": repo.check_cron_expression,
                "last_scheduled_check": serialize_datetime(repo.last_scheduled_check),
                "next_scheduled_check": serialize_datetime(repo.next_scheduled_check),
                "check_max_duration": repo.check_max_duration,
                "notify_on_check_success": repo.notify_on_check_success,
                "notify_on_check_failure": repo.notify_on_check_failure
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update check schedule", error=str(e), repo_id=repo_id)
        raise HTTPException(status_code=500, detail=f"Failed to update check schedule: {str(e)}")

@router.get("/{repo_id}/check-schedule")
async def get_check_schedule(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get scheduled check configuration for repository"""
    try:
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        return {
            "repository_id": repo.id,
            "repository_name": repo.name,
            "repository_path": repo.path,
            "check_cron_expression": repo.check_cron_expression,
            "last_scheduled_check": serialize_datetime(repo.last_scheduled_check),
            "next_scheduled_check": serialize_datetime(repo.next_scheduled_check),
            "check_max_duration": repo.check_max_duration,
            "notify_on_check_success": repo.notify_on_check_success,
            "notify_on_check_failure": repo.notify_on_check_failure,
            "enabled": repo.check_cron_expression is not None and repo.check_cron_expression != ""
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get check schedule", error=str(e), repo_id=repo_id)
        raise HTTPException(status_code=500, detail=f"Failed to get check schedule: {str(e)}")
