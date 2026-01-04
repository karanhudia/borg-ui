from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import structlog

from app.database.database import get_db, engine
from app.database.models import User, SSHKey, SSHConnection, Repository, BackupJob, SystemSettings
from app.core.security import get_current_user, get_password_hash, verify_password
from sqlalchemy import text
from app.core.borg import BorgInterface
from app.config import settings as app_settings

logger = structlog.get_logger()
router = APIRouter(tags=["settings"])

# Initialize Borg interface
borg = BorgInterface()

# Pydantic models for request/response
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool = False

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class PasswordReset(BaseModel):
    new_password: str

class SystemSettingsUpdate(BaseModel):
    backup_timeout: Optional[int] = None
    max_concurrent_backups: Optional[int] = None
    log_retention_days: Optional[int] = None
    log_save_policy: Optional[str] = None
    log_max_total_size_mb: Optional[int] = None
    log_cleanup_on_startup: Optional[bool] = None
    borg_info_timeout: Optional[int] = None
    borg_list_timeout: Optional[int] = None
    borg_init_timeout: Optional[int] = None
    borg_general_timeout: Optional[int] = None
    email_notifications: Optional[bool] = None
    webhook_url: Optional[str] = None
    auto_cleanup: Optional[bool] = None
    cleanup_retention_days: Optional[int] = None

@router.get("/system")
async def get_system_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system settings"""
    try:
        # Get settings from database or use defaults
        settings = db.query(SystemSettings).first()
        if not settings:
            # Create default settings
            settings = SystemSettings(
                backup_timeout=3600,
                max_concurrent_backups=2,
                log_retention_days=30,
                email_notifications=False,
                webhook_url="",
                auto_cleanup=True,
                cleanup_retention_days=90
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
        
        # Get log storage statistics
        from app.services.log_manager import log_manager
        try:
            log_storage = log_manager.calculate_log_storage()
            usage_percent = 0
            if settings.log_max_total_size_mb and settings.log_max_total_size_mb > 0:
                usage_percent = min(100, int((log_storage["total_size_mb"] / settings.log_max_total_size_mb) * 100))

            log_storage_info = {
                "total_size_mb": log_storage["total_size_mb"],
                "file_count": log_storage["file_count"],
                "oldest_log_date": log_storage["oldest_log_date"].isoformat() if log_storage["oldest_log_date"] else None,
                "newest_log_date": log_storage["newest_log_date"].isoformat() if log_storage["newest_log_date"] else None,
                "usage_percent": usage_percent,
                "files_by_type": log_storage["files_by_type"]
            }
        except Exception as e:
            logger.warning("Failed to calculate log storage", error=str(e))
            log_storage_info = {
                "total_size_mb": 0,
                "file_count": 0,
                "oldest_log_date": None,
                "newest_log_date": None,
                "usage_percent": 0,
                "files_by_type": {}
            }

        return {
            "success": True,
            "settings": {
                "backup_timeout": settings.backup_timeout,
                "max_concurrent_backups": settings.max_concurrent_backups,
                "log_retention_days": settings.log_retention_days,
                "log_save_policy": settings.log_save_policy,
                "log_max_total_size_mb": settings.log_max_total_size_mb,
                "log_cleanup_on_startup": settings.log_cleanup_on_startup,
                "email_notifications": settings.email_notifications,
                "webhook_url": settings.webhook_url,
                "auto_cleanup": settings.auto_cleanup,
                "cleanup_retention_days": settings.cleanup_retention_days,
                "borg_version": borg.get_version(),
                "app_version": "1.36.1"
            },
            "log_storage": log_storage_info
        }
    except Exception as e:
        logger.error("Failed to get system settings", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve system settings: {str(e)}")

@router.put("/system")
async def update_system_settings(
    settings_update: SystemSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update system settings (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Validate log management settings
        warnings = []

        if settings_update.log_save_policy is not None:
            valid_policies = ["failed_only", "failed_and_warnings", "all_jobs"]
            if settings_update.log_save_policy not in valid_policies:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid log_save_policy. Must be one of: {', '.join(valid_policies)}"
                )

        if settings_update.log_max_total_size_mb is not None:
            if settings_update.log_max_total_size_mb < 10:
                raise HTTPException(
                    status_code=400,
                    detail="log_max_total_size_mb must be at least 10 MB"
                )

            # Check if new limit is below current usage
            from app.services.log_manager import log_manager
            try:
                log_storage = log_manager.calculate_log_storage()
                if log_storage["total_size_mb"] > settings_update.log_max_total_size_mb:
                    warnings.append(
                        f"Warning: Current log storage ({log_storage['total_size_mb']} MB) exceeds new limit "
                        f"({settings_update.log_max_total_size_mb} MB). Consider running log cleanup."
                    )
            except Exception as e:
                logger.warning("Failed to check log storage for validation", error=str(e))

        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)

        # Update settings
        if settings_update.backup_timeout is not None:
            settings.backup_timeout = settings_update.backup_timeout
        if settings_update.max_concurrent_backups is not None:
            settings.max_concurrent_backups = settings_update.max_concurrent_backups
        if settings_update.log_retention_days is not None:
            settings.log_retention_days = settings_update.log_retention_days
        if settings_update.log_save_policy is not None:
            settings.log_save_policy = settings_update.log_save_policy
        if settings_update.log_max_total_size_mb is not None:
            settings.log_max_total_size_mb = settings_update.log_max_total_size_mb
        if settings_update.log_cleanup_on_startup is not None:
            settings.log_cleanup_on_startup = settings_update.log_cleanup_on_startup
        if settings_update.email_notifications is not None:
            settings.email_notifications = settings_update.email_notifications
        if settings_update.webhook_url is not None:
            settings.webhook_url = settings_update.webhook_url
        if settings_update.auto_cleanup is not None:
            settings.auto_cleanup = settings_update.auto_cleanup
        if settings_update.cleanup_retention_days is not None:
            settings.cleanup_retention_days = settings_update.cleanup_retention_days

        settings.updated_at = datetime.utcnow()
        db.commit()

        logger.info("System settings updated", user=current_user.username)

        response = {
            "success": True,
            "message": "System settings updated successfully"
        }
        if warnings:
            response["warnings"] = warnings

        return response
    except HTTPException:
        # Re-raise HTTP exceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error("Failed to update system settings", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update system settings: {str(e)}")

@router.get("/users")
async def get_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all users (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        users = db.query(User).all()
        return {
            "success": True,
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_admin": user.is_admin,
                    "created_at": user.created_at,
                    "last_login": user.last_login
                }
                for user in users
            ]
        }
    except Exception as e:
        logger.error("Failed to get users", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve users: {str(e)}")

@router.post("/users")
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new user (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Check if username already exists
        existing_user = db.query(User).filter(User.username == user_data.username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")
        
        # Check if email already exists
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already exists")
        
        # Create new user
        hashed_password = get_password_hash(user_data.password)
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            password_hash=hashed_password,
            is_active=True,
            is_admin=user_data.is_admin
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info("User created", username=user_data.username, created_by=current_user.username)
        
        return {
            "success": True,
            "message": "User created successfully",
            "user": {
                "id": new_user.id,
                "username": new_user.username,
                "email": new_user.email,
                "is_active": new_user.is_active,
                "is_admin": new_user.is_admin
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create user", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")

@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update user fields
        if user_data.username is not None:
            # Check if username already exists
            existing_user = db.query(User).filter(
                User.username == user_data.username,
                User.id != user_id
            ).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Username already exists")
            user.username = user_data.username
        
        if user_data.email is not None:
            # Check if email already exists
            existing_email = db.query(User).filter(
                User.email == user_data.email,
                User.id != user_id
            ).first()
            if existing_email:
                raise HTTPException(status_code=400, detail="Email already exists")
            user.email = user_data.email
        
        if user_data.is_active is not None:
            user.is_active = user_data.is_active
        
        if user_data.is_admin is not None:
            user.is_admin = user_data.is_admin
        
        user.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info("User updated", user_id=user_id, updated_by=current_user.username)
        
        return {
            "success": True,
            "message": "User updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update user", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete user (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prevent deleting the last admin user
        if user.is_admin:
            admin_count = db.query(User).filter(User.is_admin == True).count()
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot delete the last admin user")
        
        # Prevent deleting yourself
        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
        db.delete(user)
        db.commit()
        
        logger.info("User deleted", user_id=user_id, deleted_by=current_user.username)
        
        return {
            "success": True,
            "message": "User deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete user", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")

@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    password_data: PasswordReset,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset user password (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        hashed_password = get_password_hash(password_data.new_password)
        user.password_hash = hashed_password
        user.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info("User password reset", user_id=user_id, reset_by=current_user.username)

        return {
            "success": True,
            "message": "Password reset successfully"
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to reset user password", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to reset password: {str(e)}")

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change current user's password"""
    try:
        # Verify current password
        if not verify_password(password_data.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Update password
        hashed_password = get_password_hash(password_data.new_password)
        current_user.password_hash = hashed_password
        current_user.must_change_password = False  # Clear the flag after password change
        current_user.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info("Password changed", username=current_user.username)
        
        return {
            "success": True,
            "message": "Password changed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to change password", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")

@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user's profile"""
    return {
        "success": True,
        "profile": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "is_active": current_user.is_active,
            "is_admin": current_user.is_admin,
            "created_at": current_user.created_at,
            "last_login": current_user.last_login
        }
    }

@router.put("/profile")
async def update_profile(
    profile_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile"""
    try:
        # Update user fields
        if profile_data.username is not None:
            # Check if username already exists
            existing_user = db.query(User).filter(
                User.username == profile_data.username,
                User.id != current_user.id
            ).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Username already exists")
            current_user.username = profile_data.username
        
        if profile_data.email is not None:
            # Check if email already exists
            existing_email = db.query(User).filter(
                User.email == profile_data.email,
                User.id != current_user.id
            ).first()
            if existing_email:
                raise HTTPException(status_code=400, detail="Email already exists")
            current_user.email = profile_data.email
        
        current_user.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info("Profile updated", username=current_user.username)
        
        return {
            "success": True,
            "message": "Profile updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update profile", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")

@router.post("/system/cleanup")
async def cleanup_system(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Run system cleanup (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get system settings
        settings = db.query(SystemSettings).first()
        if not settings:
            # Create default settings if they don't exist
            settings = SystemSettings(
                backup_timeout=3600,
                max_concurrent_backups=2,
                log_retention_days=30,
                email_notifications=False,
                webhook_url="",
                auto_cleanup=True,
                cleanup_retention_days=90
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)
        
        # Perform cleanup tasks (placeholder implementation)
        cleanup_results = {
            "logs_cleaned": 0,
            "old_backups_removed": 0,
            "temp_files_cleaned": 0
        }
        
        # TODO: Implement actual cleanup logic
        # - Clean old logs based on log_retention_days
        # - Remove old backup archives based on cleanup_retention_days
        # - Clean temporary files
        
        logger.info("System cleanup completed", user=current_user.username, results=cleanup_results)
        
        return {
            "success": True,
            "message": "System cleanup completed successfully",
            "results": cleanup_results
        }
    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error occurred"
        logger.error("Failed to run system cleanup", error=error_msg)
        raise HTTPException(status_code=500, detail=f"Failed to run system cleanup: {error_msg}")

@router.get("/system/logs/storage")
async def get_log_storage_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed log storage statistics.

    Returns comprehensive information about log files including:
    - Total size and file count
    - Breakdown by job type
    - Oldest and newest log dates
    - Usage percentage against configured limit
    """
    try:
        from app.services.log_manager import log_manager

        # Get system settings for limit
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)
            db.commit()

        # Calculate log storage
        log_storage = log_manager.calculate_log_storage()

        # Calculate usage percentage
        usage_percent = 0
        if settings.log_max_total_size_mb and settings.log_max_total_size_mb > 0:
            usage_percent = min(100, int((log_storage["total_size_mb"] / settings.log_max_total_size_mb) * 100))

        return {
            "success": True,
            "storage": {
                "total_size_bytes": log_storage["total_size_bytes"],
                "total_size_mb": log_storage["total_size_mb"],
                "file_count": log_storage["file_count"],
                "oldest_log_date": log_storage["oldest_log_date"].isoformat() if log_storage["oldest_log_date"] else None,
                "newest_log_date": log_storage["newest_log_date"].isoformat() if log_storage["newest_log_date"] else None,
                "files_by_type": log_storage["files_by_type"],
                "usage_percent": usage_percent,
                "limit_mb": settings.log_max_total_size_mb,
                "retention_days": settings.log_retention_days
            }
        }
    except Exception as e:
        logger.error("Failed to get log storage stats", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get log storage statistics: {str(e)}")

@router.post("/system/logs/cleanup")
async def manual_log_cleanup(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger log cleanup based on current settings.

    This endpoint:
    - Requires admin access
    - Reads log_retention_days and log_max_total_size_mb from settings
    - Protects logs for running jobs
    - Performs age-based cleanup first, then size-based cleanup
    - Returns detailed cleanup statistics
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from app.services.log_manager import log_manager

        # Get system settings
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)
            db.commit()

        max_age_days = settings.log_retention_days or 30
        max_total_size_mb = settings.log_max_total_size_mb or 500

        logger.info("Manual log cleanup triggered",
                   user=current_user.username,
                   max_age_days=max_age_days,
                   max_total_size_mb=max_total_size_mb)

        # Run cleanup
        result = log_manager.cleanup_logs_combined(
            db=db,
            max_age_days=max_age_days,
            max_total_size_mb=max_total_size_mb,
            dry_run=False
        )

        # Get updated storage stats
        log_storage = log_manager.calculate_log_storage()

        logger.info("Manual log cleanup completed",
                   user=current_user.username,
                   deleted_count=result["total_deleted_count"],
                   size_freed_mb=result["total_deleted_size_mb"])

        return {
            "success": result["success"],
            "message": f"Log cleanup completed. Deleted {result['total_deleted_count']} files, freed {result['total_deleted_size_mb']} MB.",
            "cleanup_results": {
                "age_cleanup": {
                    "deleted_count": result["age_cleanup"]["deleted_count"],
                    "deleted_size_mb": result["age_cleanup"]["deleted_size_mb"],
                    "skipped_count": result["age_cleanup"]["skipped_count"]
                },
                "size_cleanup": {
                    "deleted_count": result["size_cleanup"]["deleted_count"],
                    "deleted_size_mb": result["size_cleanup"]["deleted_size_mb"],
                    "skipped_count": result["size_cleanup"]["skipped_count"],
                    "final_size_mb": result["size_cleanup"]["final_size_mb"]
                },
                "total_deleted_count": result["total_deleted_count"],
                "total_deleted_size_mb": result["total_deleted_size_mb"],
                "errors": result["total_errors"]
            },
            "current_storage": {
                "total_size_mb": log_storage["total_size_mb"],
                "file_count": log_storage["file_count"]
            }
        }
    except Exception as e:
        logger.error("Failed to run manual log cleanup", user=current_user.username, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to run log cleanup: {str(e)}")

 