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
from app.services.cache_service import archive_cache

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

class UserPreferencesUpdate(BaseModel):
    analytics_enabled: Optional[bool] = None
    analytics_consent_given: Optional[bool] = None

class SystemSettingsUpdate(BaseModel):
    # Operation timeouts (in seconds)
    backup_timeout: Optional[int] = None
    mount_timeout: Optional[int] = None
    info_timeout: Optional[int] = None
    list_timeout: Optional[int] = None
    init_timeout: Optional[int] = None

    max_concurrent_backups: Optional[int] = None
    log_retention_days: Optional[int] = None
    log_save_policy: Optional[str] = None
    log_max_total_size_mb: Optional[int] = None
    log_cleanup_on_startup: Optional[bool] = None
    email_notifications: Optional[bool] = None
    webhook_url: Optional[str] = None
    auto_cleanup: Optional[bool] = None
    cleanup_retention_days: Optional[int] = None
    use_new_wizard: Optional[bool] = None

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
                mount_timeout=120,
                info_timeout=600,
                list_timeout=600,
                init_timeout=300,
                max_concurrent_backups=2,
                log_retention_days=30,
                email_notifications=False,
                webhook_url="",
                auto_cleanup=True,
                cleanup_retention_days=90,
                use_new_wizard=False  # Beta features disabled by default
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
                # Operation timeouts
                "backup_timeout": settings.backup_timeout,
                "mount_timeout": settings.mount_timeout or 120,
                "info_timeout": settings.info_timeout or 600,
                "list_timeout": settings.list_timeout or 600,
                "init_timeout": settings.init_timeout or 300,
                # Other settings
                "max_concurrent_backups": settings.max_concurrent_backups,
                "log_retention_days": settings.log_retention_days,
                "log_save_policy": settings.log_save_policy,
                "log_max_total_size_mb": settings.log_max_total_size_mb,
                "log_cleanup_on_startup": settings.log_cleanup_on_startup,
                "email_notifications": settings.email_notifications,
                "webhook_url": settings.webhook_url,
                "auto_cleanup": settings.auto_cleanup,
                "cleanup_retention_days": settings.cleanup_retention_days,
                "use_new_wizard": settings.use_new_wizard,
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
        # Operation timeouts
        if settings_update.backup_timeout is not None:
            settings.backup_timeout = settings_update.backup_timeout
        if settings_update.mount_timeout is not None:
            settings.mount_timeout = settings_update.mount_timeout
        if settings_update.info_timeout is not None:
            settings.info_timeout = settings_update.info_timeout
        if settings_update.list_timeout is not None:
            settings.list_timeout = settings_update.list_timeout
        if settings_update.init_timeout is not None:
            settings.init_timeout = settings_update.init_timeout
        # Other settings
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
        if settings_update.use_new_wizard is not None:
            settings.use_new_wizard = settings_update.use_new_wizard

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

@router.get("/preferences")
async def get_preferences(current_user: User = Depends(get_current_user)):
    """Get current user's preferences"""
    return {
        "success": True,
        "preferences": {
            "analytics_enabled": current_user.analytics_enabled if hasattr(current_user, 'analytics_enabled') else True,
            "analytics_consent_given": current_user.analytics_consent_given if hasattr(current_user, 'analytics_consent_given') else False
        }
    }

@router.put("/preferences")
async def update_preferences(
    preferences: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's preferences"""
    try:
        if preferences.analytics_enabled is not None:
            current_user.analytics_enabled = preferences.analytics_enabled
        if preferences.analytics_consent_given is not None:
            current_user.analytics_consent_given = preferences.analytics_consent_given

        current_user.updated_at = datetime.utcnow()
        db.commit()

        logger.info("User preferences updated", username=current_user.username,
                   analytics_enabled=preferences.analytics_enabled,
                   analytics_consent_given=preferences.analytics_consent_given)

        return {
            "success": True,
            "message": "Preferences updated successfully"
        }
    except Exception as e:
        logger.error("Failed to update preferences", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {str(e)}")

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


# ============================================================================
# Cache Management Endpoints
# ============================================================================

@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get cache statistics and configuration.

    Returns:
    - Backend type (redis/in-memory)
    - Cache statistics (hits, misses, hit rate, size, entry count)
    - Current settings (TTL, max size)
    - Availability status

    Accessible to all authenticated users.
    """
    try:
        # Get cache stats from service
        stats = await archive_cache.get_stats()

        # Get database settings
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)
            db.commit()

        # Combine with database settings
        stats["cache_ttl_minutes"] = settings.cache_ttl_minutes
        stats["cache_max_size_mb"] = settings.cache_max_size_mb
        stats["redis_url"] = settings.redis_url
        stats["browse_max_items"] = settings.browse_max_items
        stats["browse_max_memory_mb"] = settings.browse_max_memory_mb

        return stats

    except Exception as e:
        logger.error("Failed to get cache stats", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get cache statistics: {str(e)}")


@router.post("/cache/clear")
async def clear_cache(
    repository_id: Optional[int] = Query(None, description="Repository ID to clear cache for (or None for all)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Clear archive cache.

    - If repository_id provided: Clear cache for that repository only
    - If repository_id is None: Clear all cache entries

    Requires admin access.

    Returns:
    - Number of cache entries cleared
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        if repository_id is not None:
            # Validate repository exists
            repository = db.query(Repository).filter(Repository.id == repository_id).first()
            if not repository:
                raise HTTPException(status_code=404, detail="Repository not found")

            # Clear cache for specific repository
            cleared_count = await archive_cache.clear_repository(repository_id)
            logger.info("Cache cleared for repository",
                       user=current_user.username,
                       repository_id=repository_id,
                       cleared_count=cleared_count)

            return {
                "cleared_count": cleared_count,
                "repository_id": repository_id,
                "message": f"Cleared {cleared_count} cache entries for repository {repository_id}"
            }
        else:
            # Clear all cache
            cleared_count = await archive_cache.clear_all()
            logger.info("Cache cleared (all repositories)",
                       user=current_user.username,
                       cleared_count=cleared_count)

            return {
                "cleared_count": cleared_count,
                "repository_id": None,
                "message": f"Cleared all cache ({cleared_count} entries)"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to clear cache",
                    user=current_user.username,
                    repository_id=repository_id,
                    error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.put("/cache/settings")
async def update_cache_settings(
    cache_ttl_minutes: Optional[int] = Query(None, ge=1, le=10080, description="Cache TTL in minutes (1-10080)"),
    cache_max_size_mb: Optional[int] = Query(None, ge=100, le=10240, description="Max cache size in MB (100-10240)"),
    redis_url: Optional[str] = Query(None, description="External Redis URL (e.g., redis://host:6379/0)"),
    browse_max_items: Optional[int] = Query(None, ge=100_000, le=50_000_000, description="Max items to load when browsing archives (100k-50M)"),
    browse_max_memory_mb: Optional[int] = Query(None, ge=100, le=16384, description="Max memory for archive browsing in MB (100MB-16GB)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update cache settings.

    Parameters:
    - cache_ttl_minutes: Cache time-to-live in minutes (1 minute to 7 days)
    - cache_max_size_mb: Maximum cache size in megabytes (100MB to 10GB)
    - redis_url: External Redis URL (optional). Use empty string to clear and use local Redis.
    - browse_max_items: Maximum number of files to load when browsing archives (100k to 50M)
    - browse_max_memory_mb: Maximum memory allowed for archive browsing (100MB to 16GB)

    Note: TTL changes only affect new cache entries. Existing entries keep their original TTL.
    Note: Browse limits prevent OOM when viewing archives with millions of files.

    Requires admin access.

    Returns:
    - Updated settings
    - Redis connection result if redis_url was changed
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if cache_ttl_minutes is None and cache_max_size_mb is None and redis_url is None and browse_max_items is None and browse_max_memory_mb is None:
        raise HTTPException(status_code=400, detail="At least one setting must be provided")

    try:
        # Get or create system settings
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)

        # Track changes for logging
        changes = {}
        reconfigure_result = None

        # Update Redis URL if provided
        if redis_url is not None:
            old_url = settings.redis_url
            settings.redis_url = redis_url if redis_url.strip() else None
            changes["redis_url"] = {
                "old": old_url,
                "new": settings.redis_url
            }

            # Reconfigure cache service with new Redis URL
            try:
                reconfigure_result = archive_cache.reconfigure(
                    redis_url=settings.redis_url,
                    cache_max_size_mb=cache_max_size_mb or settings.cache_max_size_mb
                )

                if not reconfigure_result["success"]:
                    logger.warning("Redis reconfiguration failed, using fallback",
                                 redis_url=settings.redis_url,
                                 backend=reconfigure_result["backend"])
            except Exception as reconfig_error:
                logger.error("Failed to reconfigure cache service",
                           redis_url=settings.redis_url,
                           error=str(reconfig_error))
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to connect to Redis: {str(reconfig_error)}"
                )

        # Update TTL
        if cache_ttl_minutes is not None:
            old_ttl = settings.cache_ttl_minutes
            settings.cache_ttl_minutes = cache_ttl_minutes
            changes["cache_ttl_minutes"] = {"old": old_ttl, "new": cache_ttl_minutes}

            # Update config for new cache entries
            app_settings.cache_ttl_seconds = cache_ttl_minutes * 60

        # Update max size
        if cache_max_size_mb is not None:
            old_size = settings.cache_max_size_mb
            settings.cache_max_size_mb = cache_max_size_mb
            changes["cache_max_size_mb"] = {"old": old_size, "new": cache_max_size_mb}

            # Update config for cache service
            app_settings.cache_max_size_mb = cache_max_size_mb

            # If we didn't already reconfigure for redis_url, reconfigure for size
            if redis_url is None and reconfigure_result is None:
                try:
                    reconfigure_result = archive_cache.reconfigure(
                        cache_max_size_mb=cache_max_size_mb
                    )
                except Exception as reconfig_error:
                    logger.warning("Failed to reconfigure cache size",
                                 error=str(reconfig_error))

        # Update browse limits
        if browse_max_items is not None:
            old_items = settings.browse_max_items
            settings.browse_max_items = browse_max_items
            changes["browse_max_items"] = {"old": old_items, "new": browse_max_items}

        if browse_max_memory_mb is not None:
            old_memory = settings.browse_max_memory_mb
            settings.browse_max_memory_mb = browse_max_memory_mb
            changes["browse_max_memory_mb"] = {"old": old_memory, "new": browse_max_memory_mb}

        db.commit()

        logger.info("Cache settings updated",
                   user=current_user.username,
                   changes=changes)

        response = {
            "cache_ttl_minutes": settings.cache_ttl_minutes,
            "cache_max_size_mb": settings.cache_max_size_mb,
            "redis_url": settings.redis_url,
            "browse_max_items": settings.browse_max_items,
            "browse_max_memory_mb": settings.browse_max_memory_mb,
            "message": "Cache settings updated successfully. Note: TTL changes only affect new cache entries."
        }

        # Add reconfiguration result if available
        if reconfigure_result:
            response["backend"] = reconfigure_result["backend"]
            response["connection_info"] = reconfigure_result.get("connection_info")
            if reconfigure_result["backend"] == "redis":
                response["message"] += f" Connected to Redis: {reconfigure_result.get('connection_info', 'N/A')}"
            elif reconfigure_result["backend"] == "in-memory":
                response["message"] += " Using in-memory cache (Redis connection failed)."

        return response

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to update cache settings",
                    user=current_user.username,
                    error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update cache settings: {str(e)}")

