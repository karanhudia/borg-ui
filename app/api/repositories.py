from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import structlog
import os
import subprocess
import asyncio

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
    repository_type: str = "local"  # local, ssh, sftp
    host: Optional[str] = None  # For SSH repositories
    port: Optional[int] = 22  # SSH port
    username: Optional[str] = None  # SSH username
    ssh_key_id: Optional[int] = None  # Associated SSH key ID

class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    compression: Optional[str] = None
    is_active: Optional[bool] = None

class RepositoryInfo(BaseModel):
    id: int
    name: str
    path: str
    encryption: str
    compression: str
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
        
        # Create repository directory if local
        if repo_data.repository_type == "local":
            os.makedirs(repo_path, exist_ok=True)
        
        # Initialize Borg repository
        init_result = await initialize_borg_repository(
            repo_path, 
            repo_data.encryption, 
            repo_data.passphrase,
            repo_data.ssh_key_id if repo_data.repository_type in ["ssh", "sftp"] else None
        )
        
        if not init_result["success"]:
            raise HTTPException(status_code=500, detail=f"Failed to initialize repository: {init_result['error']}")
        
        # Create repository record
        repository = Repository(
            name=repo_data.name,
            path=repo_path,
            encryption=repo_data.encryption,
            compression=repo_data.compression,
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

async def initialize_borg_repository(path: str, encryption: str, passphrase: str = None, ssh_key_id: int = None) -> Dict[str, Any]:
    """Initialize a new Borg repository"""
    try:
        # Check if borg is available
        try:
            # Test if borg command exists
            test_process = await asyncio.create_subprocess_exec(
                "borg", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await test_process.communicate()
            if test_process.returncode != 0:
                raise FileNotFoundError("borg command not found")
        except (FileNotFoundError, OSError) as e:
            logger.error("Borg not available", error=str(e))
            return {
                "success": False,
                "error": f"Borg not available: {str(e)}"
            }
        
        # Build borg init command
        cmd = ["borg", "init", "--encryption", encryption]
        
        # Set up environment
        env = os.environ.copy()
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase
        
        # Handle SSH key for remote repositories
        if ssh_key_id and path.startswith("ssh://"):
            # Get SSH key from database
            from app.database.models import SSHKey
            from app.database.database import get_db
            from cryptography.fernet import Fernet
            import base64
            
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
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write(private_key)
                temp_key_file = f.name

            # Set restrictive permissions on private key file (required by SSH)
            os.chmod(temp_key_file, 0o600)

            # Set SSH key environment variable
            env["BORG_RSH"] = f"ssh -i {temp_key_file} -o StrictHostKeyChecking=no"
        
        # Add repository path
        cmd.append(path)
        
        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        
        if process.returncode == 0:
            return {
                "success": True,
                "message": "Repository initialized successfully"
            }
        else:
            return {
                "success": False,
                "error": stderr.decode() if stderr else "Unknown error"
            }
    except Exception as e:
        logger.error("Failed to initialize repository", error=str(e))
        return {
            "success": False,
            "error": str(e)
        }

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
