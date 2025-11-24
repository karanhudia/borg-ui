from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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

class SSHConnectionTest(BaseModel):
    host: str
    username: str
    port: int = 22

class SSHConnectionInfo(BaseModel):
    id: int
    host: str
    username: str
    port: int
    status: str
    last_test: Optional[str]
    last_success: Optional[str]
    error_message: Optional[str]
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
            db.commit()
        else:
            # Create new connection record
            existing_connection = SSHConnection(
                ssh_key_id=key_id,
                host=connection_data.host,
                username=connection_data.username,
                port=connection_data.port,
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
    """Get all SSH connections"""
    try:
        connections = db.query(SSHConnection).all()
        return {
            "success": True,
            "connections": [
                {
                    "id": conn.id,
                    "ssh_key_id": conn.ssh_key_id,
                    "ssh_key_name": conn.ssh_key.name,
                    "host": conn.host,
                    "username": conn.username,
                    "port": conn.port,
                    "status": conn.status,
                    "last_test": serialize_datetime(conn.last_test),
                    "last_success": serialize_datetime(conn.last_success),
                    "error_message": conn.error_message,
                    "created_at": serialize_datetime(conn.created_at)
                }
                for conn in connections
            ]
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
    """Delete SSH key (system key cannot be deleted via this endpoint)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        ssh_key = db.query(SSHKey).filter(SSHKey.id == key_id).first()
        if not ssh_key:
            raise HTTPException(status_code=404, detail="SSH key not found")

        # Prevent deletion of system key
        if ssh_key.is_system_key:
            raise HTTPException(
                status_code=403,
                detail="Cannot delete the system SSH key. This is the primary key used for all remote connections."
            )

        # Check if key is used by any repositories
        if ssh_key.repositories:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete SSH key that is used by repositories. Remove from repositories first."
            )

        key_name = ssh_key.name
        db.delete(ssh_key)
        db.commit()

        logger.info("SSH key deleted", name=key_name, user=current_user.username)

        return {
            "success": True,
            "message": "SSH key deleted successfully"
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
        cmd = [
            "sshpass", "-p", password,
            "ssh-copy-id",
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

        logger.info(
            "ssh_key_file_created_for_test",
            key_id=ssh_key.id,
            key_file=key_file_path
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
