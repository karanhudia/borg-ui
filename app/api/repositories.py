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
from app.core.borgmatic import BorgmaticInterface
from app.config import settings

logger = structlog.get_logger()
router = APIRouter(tags=["repositories"])

# Initialize Borgmatic interface
borgmatic = BorgmaticInterface()

# Pydantic models
from pydantic import BaseModel

class RepositoryCreate(BaseModel):
    name: str
    path: str
    encryption: str = "repokey"  # repokey, keyfile, none
    compression: str = "lz4"  # lz4, zstd, zlib, none
    passphrase: Optional[str] = None
    source_directories: Optional[List[str]] = None  # List of directories to backup
    repository_type: str = "local"  # local, ssh, sftp
    host: Optional[str] = None  # For SSH repositories
    port: Optional[int] = 22  # SSH port
    username: Optional[str] = None  # SSH username
    ssh_key_id: Optional[int] = None  # Associated SSH key ID

class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    compression: Optional[str] = None
    source_directories: Optional[List[str]] = None
    is_active: Optional[bool] = None

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
                    "last_backup": repo.last_backup.isoformat() if repo.last_backup else None,
                    "total_size": repo.total_size,
                    "archive_count": repo.archive_count,
                    "is_active": repo.is_active,
                    "created_at": repo.created_at.isoformat(),
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None
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
                # If relative path, make it relative to backup path
                repo_path = os.path.join(settings.borgmatic_backup_path, repo_path)

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
            logger.info("Checking if borg/borgmatic is installed on remote machine",
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
                       has_borgmatic=remote_check.get("has_borgmatic"),
                       borg_path=remote_check.get("borg_path"))

            # Build SSH repository path
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

        # Create repository record
        repository = Repository(
            name=repo_data.name,
            path=repo_path,
            encryption=repo_data.encryption,
            compression=repo_data.compression,
            passphrase=repo_data.passphrase,  # Store passphrase for backups
            source_directories=source_directories_json,
            is_active=True,
            repository_type=repo_data.repository_type,
            host=repo_data.host,
            port=repo_data.port,
            username=repo_data.username,
            ssh_key_id=repo_data.ssh_key_id
        )
        
        db.add(repository)
        db.commit()
        db.refresh(repository)
        
        logger.info("Repository created", name=repo_data.name, path=repo_path, user=current_user.username)
        
        return {
            "success": True,
            "message": "Repository created successfully",
            "repository": {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path,
                "encryption": repository.encryption,
                "compression": repository.compression,
                "is_active": repository.is_active
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create repository: {str(e)}")

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
                "last_backup": repository.last_backup.isoformat() if repository.last_backup else None,
                "total_size": repository.total_size,
                "archive_count": repository.archive_count,
                "is_active": repository.is_active,
                "created_at": repository.created_at.isoformat(),
                "updated_at": repository.updated_at.isoformat() if repository.updated_at else None,
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

        if repo_data.is_active is not None:
            repository.is_active = repo_data.is_active
        
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
        archives_result = await borgmatic.list_archives(repository.path)
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
        check_result = await borgmatic.check_repository(repository.path)
        
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
        compact_result = await borgmatic.compact_repository(repository.path)
        
        return {
            "success": True,
            "compact_result": compact_result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to compact repository", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to compact repository: {str(e)}")

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
    """Check if borg/borgmatic is installed on remote machine"""
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
                "has_borg": False,
                "has_borgmatic": False
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

        # Check for borgmatic
        borgmatic_cmd = [
            "ssh", "-i", temp_key_file,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-p", str(port),
            f"{username}@{host}",
            "which borgmatic"
        ]

        borgmatic_process = await asyncio.create_subprocess_exec(
            *borgmatic_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        borgmatic_stdout, borgmatic_stderr = await asyncio.wait_for(borgmatic_process.communicate(), timeout=15)
        has_borgmatic = borgmatic_process.returncode == 0

        logger.info("Remote borg check completed",
                   host=host,
                   has_borg=has_borg,
                   has_borgmatic=has_borgmatic)

        return {
            "success": True,
            "has_borg": has_borg,
            "has_borgmatic": has_borgmatic,
            "borg_path": borg_stdout.decode().strip() if has_borg else None,
            "borgmatic_path": borgmatic_stdout.decode().strip() if has_borgmatic else None
        }

    except asyncio.TimeoutError:
        logger.error("Remote borg check timed out", host=host)
        return {
            "success": False,
            "error": "Connection timeout while checking remote borg installation",
            "has_borg": False,
            "has_borgmatic": False
        }
    except Exception as e:
        logger.error("Failed to check remote borg installation", host=host, error=str(e))
        return {
            "success": False,
            "error": str(e),
            "has_borg": False,
            "has_borgmatic": False
        }
    finally:
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
                "message": "Repository initialized successfully"
            }
        else:
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
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Build borg list command
        cmd = ["borg", "list", "--json", repository.path]

        # Set up environment
        env = os.environ.copy()
        if repository.passphrase:
            env["BORG_PASSPHRASE"] = repository.passphrase

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error("Failed to list archives", error=error_msg)
            raise HTTPException(status_code=500, detail=f"Failed to list archives: {error_msg}")

        # Parse JSON output
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
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse borg list output", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to parse archive list")
    except Exception as e:
        logger.error("Failed to list archives", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list archives: {str(e)}")

@router.get("/{repo_id}/info")
async def get_repository_info(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed repository information using borg info"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Build borg info command
        cmd = ["borg", "info", "--json", repository.path]

        # Set up environment
        env = os.environ.copy()
        if repository.passphrase:
            env["BORG_PASSPHRASE"] = repository.passphrase

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error("Failed to get repository info", error=error_msg)
            raise HTTPException(status_code=500, detail=f"Failed to get repository info: {error_msg}")

        # Parse JSON output
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
async def get_archive_info(
    repo_id: int,
    archive_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed archive information using borg info repo::archive"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Build borg info command with repo::archive format
        archive_path = f"{repository.path}::{archive_name}"
        cmd = ["borg", "info", "--json", archive_path]

        # Set up environment
        env = os.environ.copy()
        if repository.passphrase:
            env["BORG_PASSPHRASE"] = repository.passphrase

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

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

        logger.info("Archive info retrieved successfully",
                   repo_id=repo_id,
                   archive_name=archive_name)

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

async def get_repository_stats(path: str) -> Dict[str, Any]:
    """Get repository statistics"""
    try:
        # Get repository info
        info_result = await borgmatic._execute_command(["borg", "info", path])

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
        archives_result = await borgmatic.list_archives(path)
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
