from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import structlog
import os
import subprocess
import asyncio
import tempfile
from cryptography.fernet import Fernet
import base64

from app.database.database import get_db
from app.database.models import User, SSHKey, SSHConnection
from app.core.security import get_current_user
from app.config import settings
from app.utils.datetime_utils import serialize_datetime
import hashlib

logger = structlog.get_logger()
router = APIRouter(tags=["ssh-keys"])

# Helper functions
def format_bytes(bytes_size: int) -> str:
    """Format bytes to human readable string (e.g., '1.23 GB')"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} EB"

async def _run_df_command(connection: SSHConnection, temp_key_file: str, check_path: str, use_locale: bool) -> Optional[Dict[str, Any]]:
    """
    Run df command and parse output.
    Returns parsed storage info or None if command fails or output can't be parsed.
    """
    df_command = f"LC_ALL=C df -k {check_path}" if use_locale else f"df -k {check_path}"

    df_cmd = [
        "ssh",
        "-i", temp_key_file,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=10",
        "-p", str(connection.port),
        f"{connection.username}@{connection.host}",
        df_command
    ]

    process = await asyncio.create_subprocess_exec(
        *df_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)

    if process.returncode != 0:
        return None

    output = stdout.decode().strip()
    if not output:
        return None

    # Parse df output - skip header line (works for any language)
    # Format: Filesystem 1K-blocks Used Available Use% Mounted
    # German: Dateisystem 1K-Blöcke Benutzt Verfügbar Verw% Eingehängt
    lines = output.split('\n')
    data_line = None

    for line in lines:
        if not line.strip():
            continue
        # Header line typically has non-numeric second column
        parts = line.split()
        if len(parts) >= 5:
            # Try to parse second column as number - if it works, this is a data line
            try:
                int(parts[1])
                data_line = line
                break
            except ValueError:
                # This is likely a header line, skip it
                continue

    if not data_line:
        return None

    parts = data_line.split()
    if len(parts) >= 5:
        try:
            total_kb = int(parts[1])
            used_kb = int(parts[2])
            available_kb = int(parts[3])
            percent_str = parts[4].rstrip('%')

            return {
                "total": total_kb * 1024,  # Convert to bytes
                "used": used_kb * 1024,
                "available": available_kb * 1024,
                "percent_used": float(percent_str),
                "filesystem": parts[0],
                "mount_point": parts[5] if len(parts) > 5 else check_path
            }
        except (ValueError, IndexError):
            return None

    return None


async def collect_storage_info(connection: SSHConnection, ssh_key: SSHKey) -> Optional[Dict[str, Any]]:
    """
    Collect storage information for an SSH connection using df command.
    Returns dict with storage info or None if collection fails.

    Tries with LC_ALL=C first for consistent English output, then falls back
    to plain df for restricted shells (like Hetzner Storage Box) that don't
    support environment variable assignment.
    """
    try:
        # Decrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

        if not private_key.endswith('\n'):
            private_key += '\n'

        # Create temporary key file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(private_key)
            temp_key_file = f.name

        os.chmod(temp_key_file, 0o600)

        try:
            check_path = connection.default_path or "/"

            # Try with LC_ALL=C first (ensures English output on normal systems)
            result = await _run_df_command(connection, temp_key_file, check_path, use_locale=True)

            if result:
                return result

            # Fallback: try without locale prefix (for restricted shells like Hetzner)
            # The parser handles non-English output by detecting numeric columns
            result = await _run_df_command(connection, temp_key_file, check_path, use_locale=False)

            if result:
                return result

            logger.warning("Failed to get remote disk usage",
                         connection_id=connection.id)
            return None

        finally:
            # Clean up temporary key file
            if os.path.exists(temp_key_file):
                try:
                    os.unlink(temp_key_file)
                except:
                    pass

    except asyncio.TimeoutError:
        logger.warning("Timeout getting remote disk usage", connection_id=connection.id)
        return None
    except Exception as e:
        logger.error("Failed to collect storage info",
                   connection_id=connection.id,
                   error=str(e))
        return None

# Pydantic models
from pydantic import BaseModel

class SSHKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    key_type: str = "rsa"  # rsa, ed25519, ecdsa
    public_key: str
    private_key: str

class SSHKeyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class SSHKeyInfo(BaseModel):
    id: int
    name: str
    description: Optional[str]
    key_type: str
    public_key: str
    is_active: bool
    created_at: str
    updated_at: Optional[str]

class SSHKeyGenerate(BaseModel):
    name: str
    key_type: str = "rsa"
    description: Optional[str] = None

class SSHQuickSetup(BaseModel):
    name: str
    key_type: str = "rsa"
    description: Optional[str] = None
    comment: Optional[str] = None
    host: Optional[str] = None
    username: Optional[str] = None
    port: int = 22
    password: Optional[str] = None
    skip_deployment: bool = False

class SSHConnectionCreate(BaseModel):
    host: str
    username: str
    port: int = 22
    password: str
    default_path: Optional[str] = None  # Default starting path for SSH browsing
    mount_point: Optional[str] = None  # Logical mount point (e.g., /hetzner)

class SSHConnectionTest(BaseModel):
    host: str
    username: str
    port: int = 22

class SSHConnectionUpdate(BaseModel):
    host: Optional[str] = None
    username: Optional[str] = None
    port: Optional[int] = None
    default_path: Optional[str] = None  # Default starting path for SSH browsing
    mount_point: Optional[str] = None  # Logical mount point

class SSHConnectionStorage(BaseModel):
    total: int
    total_formatted: str
    used: int
    used_formatted: str
    available: int
    available_formatted: str
    percent_used: float
    last_check: Optional[str]

class SSHConnectionInfo(BaseModel):
    id: int
    host: str
    username: str
    port: int
    default_path: Optional[str]  # Default starting path for SSH browsing
    mount_point: Optional[str]  # Logical mount point
    status: str
    last_test: Optional[str]
    last_success: Optional[str]
    error_message: Optional[str]
    storage: Optional[SSHConnectionStorage]  # Storage information
    created_at: str

@router.get("/system-key")
async def get_system_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the system SSH key (there can be only one)"""
    try:
        system_key = db.query(SSHKey).filter(SSHKey.is_system_key == True).first()

        if not system_key:
            return {
                "success": True,
                "exists": False,
                "ssh_key": None
            }

        return {
            "success": True,
            "exists": True,
            "ssh_key": {
                "id": system_key.id,
                "name": system_key.name,
                "description": system_key.description,
                "key_type": system_key.key_type,
                "public_key": system_key.public_key,
                "fingerprint": system_key.fingerprint,
                "is_active": system_key.is_active,
                "created_at": serialize_datetime(system_key.created_at),
                "updated_at": serialize_datetime(system_key.updated_at),
                "connection_count": len(system_key.connections),
                "active_connections": len([c for c in system_key.connections if c.status == "connected"])
            }
        }
    except Exception as e:
        logger.error("Failed to get system SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve system SSH key: {str(e)}")

@router.get("")
@router.get("/")
async def get_ssh_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all SSH keys with connection status (deprecated - use /system-key)"""
    try:
        ssh_keys = db.query(SSHKey).all()
        return {
            "success": True,
            "ssh_keys": [
                {
                    "id": key.id,
                    "name": key.name,
                    "description": key.description,
                    "key_type": key.key_type,
                    "public_key": key.public_key,
                    "fingerprint": key.fingerprint,
                    "is_system_key": key.is_system_key,
                    "is_active": key.is_active,
                    "created_at": serialize_datetime(key.created_at),
                    "updated_at": serialize_datetime(key.updated_at),
                    "connection_count": len(key.connections),
                    "active_connections": len([c for c in key.connections if c.status == "connected"])
                }
                for key in ssh_keys
            ]
        }
    except Exception as e:
        logger.error("Failed to get SSH keys", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve SSH keys: {str(e)}")

@router.post("")
@router.post("/")
async def create_ssh_key(
    key_data: SSHKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new SSH key"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Check if SSH key name already exists
        existing_key = db.query(SSHKey).filter(SSHKey.name == key_data.name).first()
        if existing_key:
            raise HTTPException(status_code=400, detail="SSH key name already exists")
        
        # Validate SSH key format
        if not key_data.public_key.startswith(('ssh-rsa', 'ssh-ed25519', 'ecdsa-sha2')):
            raise HTTPException(status_code=400, detail="Invalid public key format")
        
        # Encrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        encrypted_private_key = cipher.encrypt(key_data.private_key.encode()).decode()
        
        # Create SSH key record
        ssh_key = SSHKey(
            name=key_data.name,
            description=key_data.description,
            key_type=key_data.key_type,
            public_key=key_data.public_key,
            private_key=encrypted_private_key,
            is_active=True
        )
        
        db.add(ssh_key)
        db.commit()
        db.refresh(ssh_key)
        
        logger.info("SSH key created", name=key_data.name, user=current_user.username)
        
        return {
            "success": True,
            "message": "SSH key created successfully",
            "ssh_key": {
                "id": ssh_key.id,
                "name": ssh_key.name,
                "description": ssh_key.description,
                "key_type": ssh_key.key_type,
                "public_key": ssh_key.public_key,
                "is_active": ssh_key.is_active
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create SSH key: {str(e)}")

class SSHKeyGenerate(BaseModel):
    name: str
    key_type: str = "rsa"
    description: Optional[str] = None

class SSHKeyImport(BaseModel):
    name: str
    private_key_path: str
    public_key_path: Optional[str] = None  # If not provided, will try {private_key_path}.pub
    description: Optional[str] = None

@router.post("/generate")
async def generate_ssh_key(
    key_data: SSHKeyGenerate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate the system SSH key (one-time only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Check if system key already exists
        existing_system_key = db.query(SSHKey).filter(SSHKey.is_system_key == True).first()
        if existing_system_key:
            raise HTTPException(
                status_code=400,
                detail="System SSH key already exists. Only one system key is allowed. Delete the existing key first if you want to generate a new one."
            )

        # Validate key type
        valid_types = ["rsa", "ed25519", "ecdsa"]
        if key_data.key_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid key type. Must be one of: {', '.join(valid_types)}")

        # Generate SSH key pair
        key_result = await generate_ssh_key_pair(key_data.key_type)

        if not key_result["success"]:
            raise HTTPException(status_code=500, detail=f"Failed to generate SSH key: {key_result['error']}")

        # Generate fingerprint
        fingerprint = await generate_ssh_key_fingerprint(key_result["public_key"])

        # Encrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        encrypted_private_key = cipher.encrypt(key_result["private_key"].encode()).decode()

        # Create system SSH key record
        ssh_key = SSHKey(
            name=key_data.name or "System SSH Key",
            description=key_data.description or "System SSH key for all remote connections",
            key_type=key_data.key_type,
            public_key=key_result["public_key"],
            private_key=encrypted_private_key,
            fingerprint=fingerprint,
            is_system_key=True,
            is_active=True
        )

        db.add(ssh_key)
        db.commit()
        db.refresh(ssh_key)

        logger.info("System SSH key generated", name=ssh_key.name, key_type=key_data.key_type, fingerprint=fingerprint, user=current_user.username)

        # Deploy SSH key immediately to filesystem
        try:
            deploy_result = subprocess.run(
                ["python3", "/app/app/scripts/deploy_ssh_key.py"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if deploy_result.returncode == 0:
                logger.info("System SSH key deployed to filesystem", stdout=deploy_result.stdout)
            else:
                logger.warning("SSH key deployment had warnings",
                             stderr=deploy_result.stderr,
                             stdout=deploy_result.stdout)
        except Exception as e:
            logger.warning("Failed to deploy SSH key to filesystem", error=str(e))

        return {
            "success": True,
            "message": "System SSH key generated successfully",
            "ssh_key": {
                "id": ssh_key.id,
                "name": ssh_key.name,
                "description": ssh_key.description,
                "key_type": ssh_key.key_type,
                "public_key": ssh_key.public_key,
                "fingerprint": ssh_key.fingerprint,
                "is_system_key": ssh_key.is_system_key,
                "is_active": ssh_key.is_active
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate system SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate system SSH key: {str(e)}")

@router.post("/import")
async def import_ssh_key(
    key_data: SSHKeyImport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Import an existing SSH key from filesystem (e.g., mounted volume)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Check if system key already exists
        existing_system_key = db.query(SSHKey).filter(SSHKey.is_system_key == True).first()
        if existing_system_key:
            raise HTTPException(
                status_code=400,
                detail="System SSH key already exists. Only one system key is allowed. Delete the existing key first if you want to import a new one."
            )

        # Check if name already exists
        existing_name = db.query(SSHKey).filter(SSHKey.name == key_data.name).first()
        if existing_name:
            raise HTTPException(status_code=400, detail=f"SSH key with name '{key_data.name}' already exists")

        # Read private key from filesystem
        private_key_path = key_data.private_key_path
        if not os.path.exists(private_key_path):
            raise HTTPException(status_code=404, detail=f"Private key file not found: {private_key_path}")

        try:
            with open(private_key_path, 'r') as f:
                private_key = f.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read private key: {str(e)}")

        # Validate private key format
        if not private_key.strip().startswith('-----BEGIN'):
            raise HTTPException(status_code=400, detail="Invalid private key format. Must be in OpenSSH format.")

        # Determine public key path
        if key_data.public_key_path:
            public_key_path = key_data.public_key_path
        else:
            public_key_path = f"{private_key_path}.pub"

        # Read public key from filesystem
        if not os.path.exists(public_key_path):
            raise HTTPException(status_code=404, detail=f"Public key file not found: {public_key_path}")

        try:
            with open(public_key_path, 'r') as f:
                public_key = f.read().strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read public key: {str(e)}")

        # Validate public key format and detect key type
        key_type = None
        if public_key.startswith('ssh-rsa'):
            key_type = 'rsa'
        elif public_key.startswith('ssh-ed25519'):
            key_type = 'ed25519'
        elif public_key.startswith('ecdsa-sha2'):
            key_type = 'ecdsa'
        else:
            raise HTTPException(status_code=400, detail="Invalid public key format. Must start with ssh-rsa, ssh-ed25519, or ecdsa-sha2")

        # Generate fingerprint
        fingerprint = await generate_ssh_key_fingerprint(public_key)

        # Encrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        encrypted_private_key = cipher.encrypt(private_key.encode()).decode()

        # Create system SSH key record
        ssh_key = SSHKey(
            name=key_data.name,
            description=key_data.description or f"Imported SSH key from {private_key_path}",
            key_type=key_type,
            public_key=public_key,
            private_key=encrypted_private_key,
            fingerprint=fingerprint,
            is_system_key=True,
            is_active=True
        )

        db.add(ssh_key)
        db.commit()
        db.refresh(ssh_key)

        logger.info("System SSH key imported",
                   name=ssh_key.name,
                   key_type=key_type,
                   fingerprint=fingerprint,
                   private_key_path=private_key_path,
                   user=current_user.username)

        # Deploy SSH key to filesystem (this will write to /home/borg/.ssh)
        try:
            deploy_result = subprocess.run(
                ["python3", "/app/app/scripts/deploy_ssh_key.py"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if deploy_result.returncode == 0:
                logger.info("Imported SSH key deployed to /home/borg/.ssh", stdout=deploy_result.stdout)
            else:
                logger.warning("SSH key deployment had warnings",
                             stderr=deploy_result.stderr,
                             stdout=deploy_result.stdout)
        except Exception as e:
            logger.warning("Failed to deploy SSH key to filesystem", error=str(e))

        return {
            "success": True,
            "message": f"System SSH key imported successfully from {private_key_path}",
            "ssh_key": {
                "id": ssh_key.id,
                "name": ssh_key.name,
                "description": ssh_key.description,
                "key_type": ssh_key.key_type,
                "public_key": ssh_key.public_key,
                "fingerprint": ssh_key.fingerprint,
                "is_system_key": ssh_key.is_system_key,
                "is_active": ssh_key.is_active
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to import system SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to import system SSH key: {str(e)}")

@router.post("/quick-setup")
async def quick_ssh_setup(
    setup_data: SSHQuickSetup,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Quick setup: Generate SSH key and optionally deploy to remote server"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Step 1: Generate SSH key
        key_result = await generate_ssh_key_pair(setup_data.key_type)
        if not key_result["success"]:
            raise HTTPException(status_code=500, detail=f"Failed to generate SSH key: {key_result['error']}")

        # Encrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        encrypted_private_key = cipher.encrypt(key_result["private_key"].encode()).decode()

        # Create SSH key record
        ssh_key = SSHKey(
            name=setup_data.name,
            description=setup_data.description,
            key_type=setup_data.key_type,
            public_key=key_result["public_key"],
            private_key=encrypted_private_key,
            is_active=True
        )

        db.add(ssh_key)
        db.commit()
        db.refresh(ssh_key)

        # Step 2: Deploy to remote server (if not skipped)
        if not setup_data.skip_deployment and setup_data.host and setup_data.username and setup_data.password:
            deploy_result = await deploy_ssh_key_with_copy_id(
                ssh_key, setup_data.host, setup_data.username,
                setup_data.password, setup_data.port
            )

            if deploy_result["success"]:
                # Create connection record
                connection = SSHConnection(
                    ssh_key_id=ssh_key.id,
                    host=setup_data.host,
                    username=setup_data.username,
                    port=setup_data.port,
                    status="connected",
                    last_success=datetime.utcnow(),
                    last_test=datetime.utcnow()
                )
                db.add(connection)
                db.commit()

                logger.info("Quick SSH setup completed with deployment",
                           name=setup_data.name,
                           host=setup_data.host,
                           user=current_user.username)

                return {
                    "success": True,
                    "message": "SSH key generated and deployed successfully",
                    "ssh_key": {
                        "id": ssh_key.id,
                        "name": ssh_key.name,
                        "key_type": ssh_key.key_type,
                        "public_key": ssh_key.public_key
                    },
                    "connection": {
                        "host": setup_data.host,
                        "username": setup_data.username,
                        "port": setup_data.port,
                        "status": "connected"
                    }
                }
            else:
                # Key was created but deployment failed
                connection = SSHConnection(
                    ssh_key_id=ssh_key.id,
                    host=setup_data.host,
                    username=setup_data.username,
                    port=setup_data.port,
                    status="failed",
                    error_message=deploy_result.get("error", "Deployment failed"),
                    last_test=datetime.utcnow()
                )
                db.add(connection)
                db.commit()

                raise HTTPException(
                    status_code=500,
                    detail=f"SSH key generated but deployment failed: {deploy_result.get('error', 'Unknown error')}"
                )
        else:
            # Deployment skipped
            logger.info("Quick SSH setup completed without deployment",
                       name=setup_data.name,
                       user=current_user.username)

            return {
                "success": True,
                "message": "SSH key generated successfully (deployment skipped)",
                "ssh_key": {
                    "id": ssh_key.id,
                    "name": ssh_key.name,
                    "key_type": ssh_key.key_type,
                    "public_key": ssh_key.public_key
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Quick SSH setup failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Quick SSH setup failed: {str(e)}")

@router.post("/{key_id}/deploy")
async def deploy_ssh_key(
    key_id: int,
    connection_data: SSHConnectionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deploy SSH key to remote server"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get SSH key
        ssh_key = db.query(SSHKey).filter(SSHKey.id == key_id).first()
        if not ssh_key:
            raise HTTPException(status_code=404, detail="SSH key not found")
        
        # Check if connection already exists
        existing_connection = db.query(SSHConnection).filter(
            SSHConnection.ssh_key_id == key_id,
            SSHConnection.host == connection_data.host,
            SSHConnection.username == connection_data.username,
            SSHConnection.port == connection_data.port
        ).first()
        
        if existing_connection:
            # Update existing connection
            existing_connection.status = "testing"
            existing_connection.last_test = datetime.utcnow()
            if connection_data.default_path is not None:
                existing_connection.default_path = connection_data.default_path
            if connection_data.mount_point is not None:
                existing_connection.mount_point = connection_data.mount_point
            db.commit()
        else:
            # Create new connection record
            existing_connection = SSHConnection(
                ssh_key_id=key_id,
                host=connection_data.host,
                username=connection_data.username,
                port=connection_data.port,
                default_path=connection_data.default_path,
                mount_point=connection_data.mount_point,
                status="testing",
                last_test=datetime.utcnow()
            )
            db.add(existing_connection)
            db.commit()
        
        # Deploy the key
        deploy_result = await deploy_ssh_key_with_copy_id(
            ssh_key, connection_data.host, connection_data.username,
            connection_data.password, connection_data.port
        )
        
        # Update connection status
        if deploy_result["success"]:
            existing_connection.status = "connected"
            existing_connection.last_success = datetime.utcnow()
            existing_connection.error_message = None
        else:
            existing_connection.status = "failed"
            existing_connection.error_message = deploy_result.get("error", "Deployment failed")
        
        existing_connection.last_test = datetime.utcnow()
        db.commit()
        
        return {
            "success": deploy_result["success"],
            "message": "SSH key deployed successfully" if deploy_result["success"] else "SSH key deployment failed",
            "connection": {
                "id": existing_connection.id,
                "host": existing_connection.host,
                "username": existing_connection.username,
                "port": existing_connection.port,
                "status": existing_connection.status,
                "error_message": existing_connection.error_message
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to deploy SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to deploy SSH key: {str(e)}")

@router.get("/connections")
async def get_ssh_connections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all SSH connections with storage information"""
    try:
        connections = db.query(SSHConnection).all()

        result_connections = []
        for conn in connections:
            # Format storage info if available
            storage = None
            if conn.storage_total is not None:
                storage = {
                    "total": conn.storage_total,
                    "total_formatted": format_bytes(conn.storage_total),
                    "used": conn.storage_used,
                    "used_formatted": format_bytes(conn.storage_used),
                    "available": conn.storage_available,
                    "available_formatted": format_bytes(conn.storage_available),
                    "percent_used": conn.storage_percent_used,
                    "last_check": serialize_datetime(conn.last_storage_check)
                }

            result_connections.append({
                "id": conn.id,
                "ssh_key_id": conn.ssh_key_id,
                "ssh_key_name": conn.ssh_key.name if conn.ssh_key else None,
                "host": conn.host,
                "username": conn.username,
                "port": conn.port,
                "default_path": conn.default_path,
                "mount_point": conn.mount_point,
                "status": conn.status,
                "last_test": serialize_datetime(conn.last_test),
                "last_success": serialize_datetime(conn.last_success),
                "error_message": conn.error_message,
                "storage": storage,
                "created_at": serialize_datetime(conn.created_at)
            })

        return {
            "success": True,
            "connections": result_connections
        }
    except Exception as e:
        logger.error("Failed to get SSH connections", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve SSH connections: {str(e)}")

@router.post("/{key_id}/test-connection")
async def test_ssh_connection(
    key_id: int,
    connection_data: SSHConnectionTest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test SSH connection using the specified key"""
    try:
        # Get SSH key
        ssh_key = db.query(SSHKey).filter(SSHKey.id == key_id).first()
        if not ssh_key:
            raise HTTPException(status_code=404, detail="SSH key not found")
        
        # Get or create connection record
        connection = db.query(SSHConnection).filter(
            SSHConnection.ssh_key_id == key_id,
            SSHConnection.host == connection_data.host,
            SSHConnection.username == connection_data.username,
            SSHConnection.port == connection_data.port
        ).first()
        
        if not connection:
            connection = SSHConnection(
                ssh_key_id=key_id,
                host=connection_data.host,
                username=connection_data.username,
                port=connection_data.port
            )
            db.add(connection)
        
        # Update status to testing
        connection.status = "testing"
        connection.last_test = datetime.utcnow()
        db.commit()
        
        # Test connection
        test_result = await test_ssh_key_connection(ssh_key, connection_data.host, connection_data.username, connection_data.port)
        
        # Update connection status
        if test_result["success"]:
            connection.status = "connected"
            connection.last_success = datetime.utcnow()
            connection.error_message = None
        else:
            connection.status = "failed"
            connection.error_message = test_result.get("error", "Connection test failed")
        
        connection.last_test = datetime.utcnow()
        db.commit()
        
        return {
            "success": test_result["success"],
            "message": test_result.get("message", "Connection test completed"),
            "connection": {
                "id": connection.id,
                "host": connection.host,
                "username": connection.username,
                "port": connection.port,
                "status": connection.status,
                "error_message": connection.error_message
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to test SSH connection", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to test SSH connection: {str(e)}")

@router.put("/connections/{connection_id}")
async def update_ssh_connection(
    connection_id: int,
    connection_data: SSHConnectionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing SSH connection"""
    try:
        connection = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(status_code=404, detail="SSH connection not found")

        # Update connection details
        if connection_data.host is not None:
            connection.host = connection_data.host
        if connection_data.username is not None:
            connection.username = connection_data.username
        if connection_data.port is not None:
            connection.port = connection_data.port
        if connection_data.default_path is not None:
            connection.default_path = connection_data.default_path
        if connection_data.mount_point is not None:
            connection.mount_point = connection_data.mount_point
        connection.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(connection)

        logger.info("SSH connection updated", connection_id=connection_id, user=current_user.username)

        return {
            "success": True,
            "message": "SSH connection updated successfully",
            "connection": {
                "id": connection.id,
                "host": connection.host,
                "username": connection.username,
                "port": connection.port,
                "status": connection.status,
                "last_test": serialize_datetime(connection.last_test),
                "last_success": serialize_datetime(connection.last_success),
                "error_message": connection.error_message
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update SSH connection", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update SSH connection: {str(e)}")

@router.post("/connections/{connection_id}/refresh-storage")
async def refresh_connection_storage(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Refresh storage information for an SSH connection"""
    try:
        connection = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(status_code=404, detail="SSH connection not found")

        # If connection has no SSH key, link it to the system key
        ssh_key = connection.ssh_key
        if not ssh_key:
            # Get system SSH key
            system_key = db.query(SSHKey).filter(SSHKey.is_system_key == True).first()
            if not system_key:
                raise HTTPException(status_code=404, detail="No system SSH key found. Generate or import one first.")

            # Link connection to system key
            connection.ssh_key_id = system_key.id
            db.commit()
            ssh_key = system_key

            logger.info("Linked connection to system key",
                       connection_id=connection_id,
                       ssh_key_id=system_key.id)

        logger.info("Refreshing storage for SSH connection",
                   connection_id=connection_id,
                   host=connection.host)

        # Collect storage information
        storage_info = await collect_storage_info(connection, ssh_key)

        if storage_info:
            # Update connection with storage info
            connection.storage_total = storage_info["total"]
            connection.storage_used = storage_info["used"]
            connection.storage_available = storage_info["available"]
            connection.storage_percent_used = storage_info["percent_used"]
            connection.last_storage_check = datetime.utcnow()

            db.commit()
            db.refresh(connection)

            logger.info("Storage refreshed successfully",
                       connection_id=connection_id,
                       storage_collected=True)

            # Return formatted storage info
            storage = {
                "total": connection.storage_total,
                "total_formatted": format_bytes(connection.storage_total),
                "used": connection.storage_used,
                "used_formatted": format_bytes(connection.storage_used),
                "available": connection.storage_available,
                "available_formatted": format_bytes(connection.storage_available),
                "percent_used": connection.storage_percent_used,
                "last_check": serialize_datetime(connection.last_storage_check)
            }

            return {
                "success": True,
                "message": "Storage information refreshed successfully",
                "storage": storage
            }
        else:
            logger.warning("Failed to collect storage information",
                         connection_id=connection_id)
            return {
                "success": False,
                "message": "Failed to collect storage information",
                "storage": None
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to refresh storage", error=str(e), connection_id=connection_id)
        raise HTTPException(status_code=500, detail=f"Failed to refresh storage: {str(e)}")

@router.post("/connections/{connection_id}/test")
async def test_existing_connection(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test an existing SSH connection"""
    try:
        connection = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(status_code=404, detail="SSH connection not found")

        # If connection has no SSH key, link it to the system key
        ssh_key = connection.ssh_key
        if not ssh_key:
            # Get system SSH key
            system_key = db.query(SSHKey).filter(SSHKey.is_system_key == True).first()
            if not system_key:
                raise HTTPException(status_code=404, detail="No system SSH key found. Generate or import one first.")

            # Link connection to system key
            connection.ssh_key_id = system_key.id
            db.commit()
            ssh_key = system_key

            logger.info("Linked connection to system key",
                       connection_id=connection_id,
                       ssh_key_id=system_key.id)

        logger.info("Testing SSH connection",
                   connection_id=connection_id,
                   host=connection.host,
                   username=connection.username,
                   port=connection.port)

        # Update connection status to "testing"
        connection.status = "testing"
        connection.last_test = datetime.utcnow()
        db.commit()

        # Test the connection using existing test function
        test_result = await test_ssh_key_connection(
            ssh_key=ssh_key,
            host=connection.host,
            username=connection.username,
            port=connection.port
        )

        # Update connection with test results
        if test_result["success"]:
            connection.status = "connected"
            connection.last_success = datetime.utcnow()
            connection.error_message = None
            logger.info("SSH connection test successful",
                       connection_id=connection_id,
                       host=connection.host)
        else:
            connection.status = "failed"
            connection.error_message = test_result.get("error", "Connection test failed")
            logger.warning("SSH connection test failed",
                         connection_id=connection_id,
                         host=connection.host,
                         error=connection.error_message)

        db.commit()
        db.refresh(connection)

        return {
            "success": test_result["success"],
            "message": "Connection tested successfully" if test_result["success"] else "Connection test failed",
            "status": connection.status,
            "error": connection.error_message
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to test connection", error=str(e), connection_id=connection_id)
        raise HTTPException(status_code=500, detail=f"Failed to test connection: {str(e)}")

@router.post("/connections/{connection_id}/redeploy")
async def redeploy_key_to_connection(
    connection_id: int,
    password: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Redeploy the current system SSH key to an existing connection"""
    try:
        # Get the connection
        connection = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(status_code=404, detail="SSH connection not found")

        # Get system SSH key
        system_key = db.query(SSHKey).filter(SSHKey.is_system_key == True).first()
        if not system_key:
            raise HTTPException(status_code=404, detail="No system SSH key found. Generate or import one first.")

        logger.info("Redeploying SSH key to existing connection",
                   connection_id=connection_id,
                   host=connection.host,
                   username=connection.username)

        # Deploy key using existing function
        deploy_result = await deploy_ssh_key_with_copy_id(
            ssh_key=system_key,
            host=connection.host,
            username=connection.username,
            password=password,
            port=connection.port
        )

        if deploy_result["success"]:
            # Link connection to system key and update status
            connection.ssh_key_id = system_key.id
            connection.status = "connected"
            connection.last_success = datetime.utcnow()
            connection.error_message = None
            db.commit()

            logger.info("SSH key redeployed successfully",
                       connection_id=connection_id,
                       host=connection.host)

            return {
                "success": True,
                "message": "SSH key deployed successfully to this connection"
            }
        else:
            # Update connection with error
            connection.status = "failed"
            connection.error_message = deploy_result.get("error", "Failed to deploy SSH key")
            db.commit()

            logger.warning("SSH key redeployment failed",
                          connection_id=connection_id,
                          host=connection.host,
                          error=connection.error_message)

            return {
                "success": False,
                "message": "Failed to deploy SSH key",
                "error": connection.error_message
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to redeploy SSH key", error=str(e), connection_id=connection_id)
        raise HTTPException(status_code=500, detail=f"Failed to redeploy SSH key: {str(e)}")

@router.delete("/connections/{connection_id}")
async def delete_ssh_connection(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an SSH connection"""
    try:
        connection = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(status_code=404, detail="SSH connection not found")

        host = connection.host
        db.delete(connection)
        db.commit()

        logger.info("SSH connection deleted", connection_id=connection_id, host=host, user=current_user.username)

        return {
            "success": True,
            "message": "SSH connection deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete SSH connection", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete SSH connection: {str(e)}")

@router.get("/{key_id}")
async def get_ssh_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get SSH key details with connections"""
    try:
        ssh_key = db.query(SSHKey).filter(SSHKey.id == key_id).first()
        if not ssh_key:
            raise HTTPException(status_code=404, detail="SSH key not found")
        
        return {
            "success": True,
            "ssh_key": {
                "id": ssh_key.id,
                "name": ssh_key.name,
                "description": ssh_key.description,
                "key_type": ssh_key.key_type,
                "public_key": ssh_key.public_key,
                "is_active": ssh_key.is_active,
                "created_at": serialize_datetime(ssh_key.created_at),
                "updated_at": serialize_datetime(ssh_key.updated_at),
                "connections": [
                    {
                        "id": conn.id,
                        "host": conn.host,
                        "username": conn.username,
                        "port": conn.port,
                        "status": conn.status,
                        "last_test": serialize_datetime(conn.last_test),
                        "last_success": serialize_datetime(conn.last_success),
                        "error_message": conn.error_message
                    }
                    for conn in ssh_key.connections
                ]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve SSH key: {str(e)}")

@router.put("/{key_id}")
async def update_ssh_key(
    key_id: int,
    key_data: SSHKeyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update SSH key"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        ssh_key = db.query(SSHKey).filter(SSHKey.id == key_id).first()
        if not ssh_key:
            raise HTTPException(status_code=404, detail="SSH key not found")
        
        # Update fields
        if key_data.name is not None:
            # Check if name already exists
            existing_key = db.query(SSHKey).filter(
                SSHKey.name == key_data.name,
                SSHKey.id != key_id
            ).first()
            if existing_key:
                raise HTTPException(status_code=400, detail="SSH key name already exists")
            ssh_key.name = key_data.name
        
        if key_data.description is not None:
            ssh_key.description = key_data.description

        if key_data.is_active is not None:
            ssh_key.is_active = key_data.is_active

        ssh_key.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(ssh_key)
        
        logger.info("SSH key updated", name=ssh_key.name, user=current_user.username)
        
        return {
            "success": True,
            "message": "SSH key updated successfully",
            "ssh_key": {
                "id": ssh_key.id,
                "name": ssh_key.name,
                "description": ssh_key.description,
                "key_type": ssh_key.key_type,
                "public_key": ssh_key.public_key,
                "is_active": ssh_key.is_active,
                "created_at": serialize_datetime(ssh_key.created_at),
                "updated_at": serialize_datetime(ssh_key.updated_at)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update SSH key: {str(e)}")

@router.delete("/{key_id}")
async def delete_ssh_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete SSH key. Connections will be preserved but marked as failed."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        ssh_key = db.query(SSHKey).filter(SSHKey.id == key_id).first()
        if not ssh_key:
            raise HTTPException(status_code=404, detail="SSH key not found")

        key_name = ssh_key.name
        key_type = ssh_key.key_type
        connection_count = len(ssh_key.connections)
        repository_count = len(ssh_key.repositories)

        # Clear SSH key from repositories using it
        if ssh_key.repositories:
            for repo in ssh_key.repositories:
                repo.ssh_key_id = None
                repo.updated_at = datetime.utcnow()

            logger.info("Cleared SSH key from repositories",
                       key_name=key_name,
                       repository_count=repository_count)

        # Preserve connections but mark them as failed
        if ssh_key.connections:
            for connection in ssh_key.connections:
                connection.ssh_key_id = None
                connection.status = "failed"
                connection.error_message = f"SSH key '{key_name}' was deleted. Deploy a new key to restore access."
                connection.updated_at = datetime.utcnow()

            logger.info("SSH connections preserved",
                       key_name=key_name,
                       connection_count=connection_count)

        # Delete the SSH key from database
        db.delete(ssh_key)
        db.commit()

        # Remove key files from filesystem
        try:
            ssh_dir = os.path.join(settings.ssh_keys_dir or "/home/borg/.ssh")
            private_key_path = os.path.join(ssh_dir, f"id_{key_type}")
            public_key_path = os.path.join(ssh_dir, f"id_{key_type}.pub")

            if os.path.exists(private_key_path):
                os.remove(private_key_path)
                logger.info("Removed private key file", path=private_key_path)

            if os.path.exists(public_key_path):
                os.remove(public_key_path)
                logger.info("Removed public key file", path=public_key_path)
        except Exception as e:
            logger.warning("Failed to remove SSH key files from filesystem", error=str(e))

        logger.info("SSH key deleted",
                   name=key_name,
                   connection_count=connection_count,
                   repository_count=repository_count,
                   user=current_user.username)

        msg_parts = ["SSH key deleted successfully."]
        if connection_count > 0:
            msg_parts.append(f"{connection_count} connection(s) preserved.")
        if repository_count > 0:
            msg_parts.append(f"{repository_count} repository/repositories cleared.")

        return {
            "success": True,
            "message": " ".join(msg_parts)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete SSH key", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete SSH key: {str(e)}")

async def generate_ssh_key_fingerprint(public_key: str) -> str:
    """Generate SSH key fingerprint (SHA256)"""
    try:
        # Write public key to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pub', delete=False) as f:
            f.write(public_key)
            temp_pub_file = f.name

        try:
            # Use ssh-keygen to generate fingerprint
            cmd = ["ssh-keygen", "-lf", temp_pub_file, "-E", "sha256"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)

            if process.returncode == 0:
                # Parse fingerprint from output: "2048 SHA256:xxxxx user@host (RSA)"
                output = stdout.decode().strip()
                parts = output.split()
                if len(parts) >= 2:
                    # Return just the hash part (SHA256:xxxxx)
                    return parts[1]
                return output
            else:
                logger.error("Failed to generate fingerprint", error=stderr.decode())
                return "Unknown"
        finally:
            # Clean up temp file
            if os.path.exists(temp_pub_file):
                os.unlink(temp_pub_file)

    except Exception as e:
        logger.error("Failed to generate SSH key fingerprint", error=str(e))
        return "Unknown"

async def generate_ssh_key_pair(key_type: str) -> Dict[str, Any]:
    """Generate SSH key pair using ssh-keygen"""
    try:
        # Create temporary directory for key generation
        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = os.path.join(temp_dir, f"id_{key_type}")
            
            # Build ssh-keygen command
            cmd = ["ssh-keygen", "-t", key_type, "-f", key_file, "-N", ""]

            cmd_str = " ".join(cmd)
            logger.info("ssh_key_generation_started", key_type=key_type, command=cmd_str)

            # Execute command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(
                    "ssh_key_generation_failed",
                    key_type=key_type,
                    command=cmd_str,
                    return_code=process.returncode,
                    error=error_msg
                )
                return {
                    "success": False,
                    "error": f"Failed to generate {key_type} SSH key pair: {error_msg}"
                }
            
            # Read generated keys
            with open(f"{key_file}.pub", "r") as f:
                public_key = f.read().strip()

            with open(key_file, "r") as f:
                # Don't strip private key - preserve exact format including trailing newline
                private_key = f.read()
            
            return {
                "success": True,
                "public_key": public_key,
                "private_key": private_key
            }
    except Exception as e:
        logger.error("Failed to generate SSH key pair", error=str(e))
        return {
            "success": False,
            "error": str(e)
        }

async def deploy_ssh_key_with_copy_id(
    ssh_key: SSHKey,
    host: str,
    username: str,
    password: str,
    port: int = 22
) -> Dict[str, Any]:
    """Deploy SSH key using ssh-copy-id"""
    try:
        # Decrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

        # Ensure private key ends with newline (required by SSH)
        if not private_key.endswith('\n'):
            private_key += '\n'

        # Ensure SSH keys directory exists
        os.makedirs(settings.ssh_keys_dir, mode=0o700, exist_ok=True)

        # Generate unique filename based on key ID and hash
        key_hash = hashlib.md5(f"{ssh_key.id}_{host}_{username}".encode()).hexdigest()[:8]
        key_filename = f"key_{ssh_key.id}_{key_hash}"
        key_file_path = os.path.join(settings.ssh_keys_dir, key_filename)

        # Write private key to persistent directory
        with open(key_file_path, 'w') as f:
            f.write(private_key)
        os.chmod(key_file_path, 0o600)

        # Write public key (ssh-copy-id needs both)
        pub_file_path = f"{key_file_path}.pub"
        with open(pub_file_path, 'w') as f:
            f.write(ssh_key.public_key)
        os.chmod(pub_file_path, 0o644)

        logger.info(
            "ssh_key_files_created",
            key_id=ssh_key.id,
            key_file=key_file_path,
            pub_file=pub_file_path
        )

        # Use sshpass with ssh-copy-id
        # Note: Some servers (like Hetzner Storage Box) require the -s flag
        cmd = [
            "sshpass", "-p", password,
            "ssh-copy-id",
            "-s",  # Use SFTP mode (required by some servers like Hetzner Storage Box)
            "-i", key_file_path,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-p", str(port),
            f"{username}@{host}"
        ]

        # Sanitized command for logging (hide password)
        safe_cmd = " ".join(cmd[0:2] + ["***"] + cmd[3:])
        logger.info("ssh_key_deployment_started", host=host, username=username, port=port, command=safe_cmd)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        if process.returncode == 0:
            logger.info(
                "ssh_key_deployed",
                host=host,
                username=username,
                port=port,
                key_file=key_file_path
            )
            return {
                "success": True,
                "output": stdout.decode(),
                "error": None,
                "key_file": key_file_path
            }
        else:
            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""
            error_msg = stderr_str or "Deployment failed"

            # Parse common SSH errors for better user feedback
            if "Connection refused" in error_msg:
                error_summary = f"Cannot connect to {host}:{port} - SSH service may not be running"
                helpful_hint = "Check if SSH server is running and firewall allows connections"
            elif "Permission denied" in error_msg:
                error_summary = f"Authentication failed for {username}@{host} - incorrect password"
                helpful_hint = "Verify the password is correct and user exists on remote system"
            elif "Host key verification failed" in error_msg:
                error_summary = f"Host key verification failed for {host}"
                helpful_hint = "Remove old host key or disable StrictHostKeyChecking"
            elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                error_summary = f"Connection timeout to {host}:{port}"
                helpful_hint = "Check network connectivity and firewall rules"
            elif "No route to host" in error_msg:
                error_summary = f"Network unreachable - cannot route to {host}"
                helpful_hint = "Verify the host IP address and network configuration"
            else:
                error_summary = "SSH key deployment failed"
                helpful_hint = "Check SSH server logs for more details"

            logger.error(
                "ssh_key_deployment_failed",
                host=host,
                username=username,
                port=port,
                command=safe_cmd,
                key_file=key_file_path,
                return_code=process.returncode,
                error_summary=error_summary,
                helpful_hint=helpful_hint,
                stdout=stdout_str[:500] if stdout_str else None,
                stderr=stderr_str[:500] if stderr_str else None,
                full_error=error_msg
            )
            return {
                "success": False,
                "output": stdout_str,
                "error": f"{error_summary}. {helpful_hint}\n\nDetails: {error_msg}",
                "key_file": key_file_path
            }
    except asyncio.TimeoutError:
        logger.error(
            "ssh_key_deployment_timeout",
            host=host,
            username=username,
            port=port,
            timeout=30
        )
        return {
            "success": False,
            "error": f"SSH key deployment timed out after 30 seconds. Server may be slow or unresponsive."
        }
    except Exception as e:
        logger.error(
            "ssh_key_deployment_exception",
            host=host,
            username=username,
            port=port,
            error_type=type(e).__name__,
            error_message=str(e),
            error_details=repr(e)
        )
        return {
            "success": False,
            "error": f"Unexpected error during SSH key deployment: {str(e)}"
        }

async def test_ssh_key_connection(ssh_key: SSHKey, host: str, username: str, port: int) -> Dict[str, Any]:
    """Test SSH connection using the specified key"""
    try:
        # Decrypt private key
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

        # Ensure private key ends with newline (required by SSH)
        if not private_key.endswith('\n'):
            private_key += '\n'

        # Ensure SSH keys directory exists
        os.makedirs(settings.ssh_keys_dir, mode=0o700, exist_ok=True)

        # Generate unique filename based on key ID and hash
        key_hash = hashlib.md5(f"{ssh_key.id}_{host}_{username}".encode()).hexdigest()[:8]
        key_filename = f"key_{ssh_key.id}_{key_hash}"
        key_file_path = os.path.join(settings.ssh_keys_dir, key_filename)

        # Write private key to persistent directory
        with open(key_file_path, 'w') as f:
            f.write(private_key)

        # Set correct permissions for SSH private key
        os.chmod(key_file_path, 0o600)

        # Write public key (required for SSH to validate key pair)
        pub_file_path = f"{key_file_path}.pub"
        with open(pub_file_path, 'w') as f:
            f.write(ssh_key.public_key)
        os.chmod(pub_file_path, 0o644)

        logger.info(
            "ssh_key_file_created_for_test",
            key_id=ssh_key.id,
            key_file=key_file_path,
            pub_file=pub_file_path
        )

        # Test SSH connection using 'pwd' command (more compatible with restricted shells like Hetzner Storage Box)
        cmd = [
            "ssh", "-i", key_file_path, "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10", "-p", str(port),
            f"{username}@{host}", "pwd"
        ]

        cmd_str = " ".join(cmd)
        logger.info("ssh_connection_test_started", host=host, username=username, port=port, command=cmd_str)

        try:

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
            
            if process.returncode == 0:
                logger.info(
                    "ssh_connection_test_successful",
                    host=host,
                    username=username,
                    port=port,
                    key_file=key_file_path
                )
                return {
                    "success": True,
                    "message": "SSH connection successful",
                    "output": stdout.decode().strip(),
                    "key_file": key_file_path
                }
            else:
                stdout_str = stdout.decode() if stdout else ""
                stderr_str = stderr.decode() if stderr else ""
                error_msg = stderr_str or stdout_str or "SSH connection failed"

                # Parse common errors with helpful hints
                if "Command not found" in error_msg or "Command not found" in stdout_str:
                    error_summary = f"SSH connection works but remote shell is restricted"
                    helpful_hint = "Server uses restricted shell (e.g., Hetzner Storage Box). Connection is valid for borg/rsync/sftp operations."
                elif "Connection refused" in error_msg:
                    error_summary = f"Cannot connect to {host}:{port} - SSH service not accessible"
                    helpful_hint = "Verify SSH server is running and port is correct"
                elif "Permission denied" in error_msg:
                    if "publickey" in error_msg:
                        error_summary = f"SSH key not authorized on {host}"
                        helpful_hint = "The public key is not in ~/.ssh/authorized_keys on the remote server"
                    else:
                        error_summary = f"Authentication failed on {host}"
                        helpful_hint = "Key-based authentication rejected by server"
                elif "Host key verification failed" in error_msg:
                    error_summary = f"Host key verification failed for {host}"
                    helpful_hint = "Host key has changed - remove from known_hosts or disable verification"
                elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    error_summary = f"Connection timeout to {host}:{port}"
                    helpful_hint = "Check network connectivity, firewall rules, and host is reachable"
                elif "No route to host" in error_msg:
                    error_summary = f"Cannot route to {host}"
                    helpful_hint = "Host is unreachable - check IP address and routing"
                elif "Load key" in error_msg and "error in libcrypto" in error_msg:
                    error_summary = "Invalid SSH key format or permissions"
                    helpful_hint = "Key file may be corrupted or have incorrect permissions"
                else:
                    error_summary = "SSH connection test failed"
                    helpful_hint = "Check SSH server configuration and logs"

                logger.error(
                    "ssh_connection_test_failed",
                    host=host,
                    username=username,
                    port=port,
                    command=cmd_str,
                    key_file=key_file_path,
                    return_code=process.returncode,
                    error_summary=error_summary,
                    helpful_hint=helpful_hint,
                    stdout=stdout_str[:500] if stdout_str else None,
                    stderr=stderr_str[:500] if stderr_str else None,
                    full_error=error_msg
                )
                return {
                    "success": False,
                    "error": f"{error_summary}. {helpful_hint}\n\nDetails: {error_msg}",
                    "return_code": process.returncode,
                    "key_file": key_file_path
                }
        except Exception as inner_error:
            logger.error(
                "ssh_connection_test_inner_exception",
                error_type=type(inner_error).__name__,
                error=str(inner_error),
                key_file=key_file_path
            )
            raise
    except asyncio.TimeoutError:
        logger.error(
            "ssh_connection_test_timeout",
            host=host,
            username=username,
            port=port,
            timeout=15
        )
        return {
            "success": False,
            "error": f"SSH connection test timed out after 15 seconds. Host may be unreachable or very slow."
        }
    except Exception as e:
        logger.error(
            "ssh_connection_test_exception",
            host=host,
            username=username,
            port=port,
            error_type=type(e).__name__,
            error_message=str(e),
            error_details=repr(e)
        )
        return {
            "success": False,
            "error": f"Unexpected error during SSH connection test: {str(e)}"
        }

# Remote Backup Source Management

@router.patch("/connections/{connection_id}/backup-source")
async def toggle_backup_source(
    connection_id: int,
    enable: bool,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enable/disable SSH connection as backup source and verify Borg installation"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from app.services.remote_backup_service import remote_backup_service

        connection = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(status_code=404, detail="SSH connection not found")

        # If enabling, verify borg is installed on remote host
        if enable:
            logger.info("Verifying Borg on remote host", connection_id=connection_id)
            result = await remote_backup_service.verify_remote_borg(connection_id)

            if not result["installed"]:
                error_msg = result.get("error", "Borg is not installed on remote host")
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot enable as backup source: {error_msg}. Please install Borg on the remote host first."
                )

            # Update connection with borg info
            connection.is_backup_source = True
            connection.borg_version = result["version"]
            connection.borg_binary_path = result["path"]
            connection.last_borg_check = datetime.utcnow()

            logger.info("Enabled SSH connection as backup source",
                       connection_id=connection_id,
                       borg_version=result["version"])
        else:
            # Disable backup source
            connection.is_backup_source = False
            logger.info("Disabled SSH connection as backup source", connection_id=connection_id)

        db.commit()

        return {
            "success": True,
            "is_backup_source": connection.is_backup_source,
            "borg_version": connection.borg_version,
            "borg_binary_path": connection.borg_binary_path,
            "last_borg_check": serialize_datetime(connection.last_borg_check) if connection.last_borg_check else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to toggle backup source",
                    connection_id=connection_id,
                    error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to toggle backup source: {str(e)}")

@router.get("/connections/backup-sources")
async def list_backup_sources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all SSH connections enabled as backup sources"""
    try:
        sources = db.query(SSHConnection).filter(
            SSHConnection.is_backup_source == True
        ).all()

        return {
            "sources": [
                {
                    "id": s.id,
                    "name": f"{s.username}@{s.host}:{s.port}",
                    "host": s.host,
                    "username": s.username,
                    "port": s.port,
                    "borg_version": s.borg_version,
                    "borg_binary_path": s.borg_binary_path,
                    "last_borg_check": serialize_datetime(s.last_borg_check) if s.last_borg_check else None,
                    "status": s.status
                }
                for s in sources
            ]
        }
    except Exception as e:
        logger.error("Failed to list backup sources", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list backup sources: {str(e)}")

@router.post("/connections/{connection_id}/verify-borg")
async def verify_borg_installation(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify Borg is installed on remote host"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from app.services.remote_backup_service import remote_backup_service

        connection = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
        if not connection:
            raise HTTPException(status_code=404, detail="SSH connection not found")

        logger.info("Verifying Borg installation", connection_id=connection_id)
        result = await remote_backup_service.verify_remote_borg(connection_id)

        # Update connection with latest borg info if successful
        if result["installed"]:
            connection.borg_version = result["version"]
            connection.borg_binary_path = result["path"]
            connection.last_borg_check = datetime.utcnow()
            db.commit()

        return {
            "installed": result["installed"],
            "version": result.get("version"),
            "path": result.get("path"),
            "error": result.get("error"),
            "last_check": serialize_datetime(datetime.utcnow())
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to verify Borg installation",
                    connection_id=connection_id,
                    error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to verify Borg installation: {str(e)}")
