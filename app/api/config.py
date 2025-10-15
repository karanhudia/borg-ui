from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
import yaml
import structlog
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.database.database import get_db
from app.database.models import User, Configuration
from app.core.security import get_current_user, get_current_admin_user
from app.core.borgmatic import borgmatic
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()

# Pydantic models
class ConfigContent(BaseModel):
    content: str

class ConfigCreate(BaseModel):
    name: str
    description: Optional[str] = None
    content: str

class ConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None

class ConfigResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    content: str
    is_default: bool
    is_valid: bool
    validation_errors: Optional[List[str]] = None
    validation_warnings: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ConfigValidation(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []

class ConfigTemplate(BaseModel):
    name: str
    description: str
    content: str

class ConfigBackupResponse(BaseModel):
    id: int
    name: str
    description: str = None
    created_at: str

    class Config:
        from_attributes = True

# Helper function to parse validation JSON
def _parse_validation_json(json_str: Optional[str]) -> Optional[List[str]]:
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except:
        return None

# Helper function to convert DB model to response
def _config_to_response(config: Configuration) -> ConfigResponse:
    return ConfigResponse(
        id=config.id,
        name=config.name,
        description=config.description,
        content=config.content,
        is_default=config.is_default,
        is_valid=config.is_valid,
        validation_errors=_parse_validation_json(config.validation_errors),
        validation_warnings=_parse_validation_json(config.validation_warnings),
        created_at=config.created_at,
        updated_at=config.updated_at
    )

@router.get("/", response_model=List[ConfigResponse])
async def list_configurations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all configurations"""
    try:
        configs = db.query(Configuration).all()
        return [_config_to_response(config) for config in configs]
    except Exception as e:
        logger.error("Failed to list configurations", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list configurations"
        )

@router.get("/default", response_model=ConfigResponse)
async def get_default_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the default configuration"""
    try:
        config = db.query(Configuration).filter(Configuration.is_default == True).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No default configuration set"
            )
        return _config_to_response(config)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get default config", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get default configuration"
        )

@router.get("/{config_id}", response_model=ConfigResponse)
async def get_configuration(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific configuration by ID"""
    try:
        config = db.query(Configuration).filter(Configuration.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration not found"
            )
        return _config_to_response(config)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get configuration", error=str(e), config_id=config_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get configuration"
        )

@router.post("/", response_model=ConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_configuration(
    config_data: ConfigCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new configuration"""
    try:
        # Check if name already exists
        existing = db.query(Configuration).filter(Configuration.name == config_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Configuration with name '{config_data.name}' already exists"
            )

        # Validate configuration
        validation = await borgmatic.validate_config(config_data.content)

        # Create configuration
        new_config = Configuration(
            name=config_data.name,
            description=config_data.description,
            content=config_data.content,
            is_default=False,
            is_valid=validation["success"],
            validation_errors=json.dumps(validation.get("errors", [validation["error"]] if not validation["success"] else [])),
            validation_warnings=json.dumps(validation.get("warnings", []))
        )

        db.add(new_config)
        db.commit()
        db.refresh(new_config)

        logger.info("Configuration created", user=current_user.username, config_name=config_data.name)
        return _config_to_response(new_config)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to create configuration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create configuration"
        )

@router.put("/{config_id}", response_model=ConfigResponse)
async def update_configuration(
    config_id: int,
    config_data: ConfigUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Update an existing configuration"""
    try:
        config = db.query(Configuration).filter(Configuration.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration not found"
            )

        # Update fields
        if config_data.name:
            # Check if new name conflicts
            existing = db.query(Configuration).filter(
                Configuration.name == config_data.name,
                Configuration.id != config_id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Configuration with name '{config_data.name}' already exists"
                )
            config.name = config_data.name

        if config_data.description is not None:
            config.description = config_data.description

        if config_data.content:
            # Validate new content
            validation = await borgmatic.validate_config(config_data.content)
            config.content = config_data.content
            config.is_valid = validation["success"]
            config.validation_errors = json.dumps(validation.get("errors", [validation["error"]] if not validation["success"] else []))
            config.validation_warnings = json.dumps(validation.get("warnings", []))

        db.commit()
        db.refresh(config)

        logger.info("Configuration updated", user=current_user.username, config_id=config_id)
        return _config_to_response(config)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to update configuration", error=str(e), config_id=config_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configuration"
        )

@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_configuration(
    config_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete a configuration"""
    try:
        config = db.query(Configuration).filter(Configuration.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration not found"
            )

        if config.is_default:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the default configuration. Set another configuration as default first."
            )

        db.delete(config)
        db.commit()

        logger.info("Configuration deleted", user=current_user.username, config_id=config_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to delete configuration", error=str(e), config_id=config_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete configuration"
        )

@router.post("/{config_id}/set-default", response_model=ConfigResponse)
async def set_default_configuration(
    config_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Set a configuration as the default"""
    try:
        config = db.query(Configuration).filter(Configuration.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration not found"
            )

        if not config.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot set an invalid configuration as default. Please fix validation errors first."
            )

        # Remove default from all other configs
        db.query(Configuration).filter(Configuration.is_default == True).update(
            {"is_default": False}
        )

        # Set this config as default
        config.is_default = True

        # Write this config to borgmatic config file
        config_path = settings.borgmatic_config_path
        with open(config_path, 'w') as f:
            f.write(config.content)

        db.commit()
        db.refresh(config)

        logger.info("Default configuration set", user=current_user.username, config_id=config_id)
        return _config_to_response(config)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to set default configuration", error=str(e), config_id=config_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set default configuration"
        )

@router.post("/validate")
async def validate_config(
    config_data: ConfigContent,
    current_user: User = Depends(get_current_user)
):
    """Validate configuration content"""
    try:
        validation = await borgmatic.validate_config(config_data.content)
        return ConfigValidation(
            valid=validation["success"],
            errors=validation.get("errors", [validation["error"]] if not validation["success"] else []),
            warnings=validation.get("warnings", [])
        )
    except Exception as e:
        logger.error("Failed to validate config", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate configuration"
        )

@router.get("/templates")
async def get_config_templates(
    current_user: User = Depends(get_current_user)
):
    """Get available configuration templates"""
    templates = [
        ConfigTemplate(
            name="basic",
            description="Basic backup configuration",
            content="""repositories:
  - path: /path/to/repository
    label: my-backup

storage:
  compression: lz4
  encryption: repokey

retention:
  keep_daily: 7
  keep_weekly: 4
  keep_monthly: 6

consistency:
  checks:
    - repository
    - archives
  check_last: 3"""
        ),
        ConfigTemplate(
            name="encrypted",
            description="Encrypted backup configuration",
            content="""repositories:
  - path: /path/to/encrypted/repository
    label: encrypted-backup

storage:
  compression: zstd
  encryption: repokey-blake2

retention:
  keep_daily: 7
  keep_weekly: 4
  keep_monthly: 12
  keep_yearly: 3

consistency:
  checks:
    - repository
    - archives
  check_last: 3"""
        ),
        ConfigTemplate(
            name="minimal",
            description="Minimal backup configuration",
            content="""repositories:
  - path: /path/to/repository

storage:
  compression: lz4

retention:
  keep_daily: 7"""
        )
    ]
    
    return templates

@router.post("/backup")
async def backup_config(
    backup_data: ConfigContent,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Backup current configuration"""
    # TODO: Implement when ConfigBackup model is added back
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Configuration backup not implemented yet"
    )

@router.get("/backups", response_model=List[ConfigBackupResponse])
async def list_config_backups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List configuration backups"""
    # TODO: Implement when ConfigBackup model is added back
    return []

@router.get("/backups/{backup_id}")
async def get_config_backup(
    backup_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific configuration backup"""
    # TODO: Implement when ConfigBackup model is added back
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Configuration backup not found"
    )

@router.post("/restore/{backup_id}")
async def restore_config_backup(
    backup_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Restore configuration from backup"""
    # TODO: Implement when ConfigBackup model is added back
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Configuration restore not implemented yet"
    ) 